// SteamSelfGifter dev-team workflow (v2: adversarial pairs, stack specialists,
// black-box QA, coverage gates).
//
//   Workflow({ scriptPath: ".claude/workflows/dev-team.js",
//              args: { task: "<task or brief>", rounds: 2, base: "origin/master" } })
//
// Phases
//   Plan        planner (Fable): per-stack briefs, API contract, expected-failure
//               matrix, ad-hoc specialists; stops on open decisions
//   Consult     ad-hoc consultant specialists write guidance for the devs
//   Build       dev-backend ∥ dev-frontend from their briefs and the contract
//   Cross-check each dev verifies the other stack against the contract
//   Challenge   per stack: challenger attacks, dev answers, challenger escalates
//               (up to `rounds`); escalations become review findings
//   Review      correctness, security, conventions + the stack lenses
//               (python, fastapi | typescript, react, ux) + ad-hoc reviewers
//   Verify      one refuter per finding
//   Fix         findings routed to the owning dev (or docs-writer), re-reviewed
//   Tests       test-engineer writes black-box tests from the failure matrix;
//               bugs it proves go back to the devs
//   Docs        docs-writer aligns docs/API.md, BACKEND_ARCHITECTURE.md, TOFIX.md, README and CLAUDE.md
//   QA          full suite + coverage gate (95% on changed lines) + shortcut
//               audit + flake runs; one repair round
//
// Resume after the planner stops: args.decisions (free text) or args.proceed=true.
// args.plan=false skips planning when the task already is a vetted brief
// (then args.stacks must say which stacks it touches).
// Every worker runs on Opus; the planner and the orchestrator run on Fable.

export const meta = {
  name: 'dev-team',
  description: 'Plan, build per stack with adversarial challengers, review with stack specialists, refute, fix, black-box test, docs, QA with coverage gates',
  whenToUse: 'Any non-trivial SteamSelfGifter change that should go through the full adversarial pipeline without the orchestrator doing the work itself',
  phases: [
    { title: 'Plan', detail: 'briefs, contract, failure matrix, specialists; stops on decisions' },
    { title: 'Consult', detail: 'ad-hoc consultants advise the devs' },
    { title: 'Build', detail: 'backend and frontend devs in parallel' },
    { title: 'Cross-check', detail: 'each dev verifies the other stack against the contract' },
    { title: 'Challenge', detail: 'same-stack challenger vs dev, up to N rounds' },
    { title: 'Review', detail: 'three core lenses + stack specialists + ad-hoc reviewers' },
    { title: 'Verify', detail: 'one refuter per finding' },
    { title: 'Fix', detail: 'owning dev fixes confirmed findings' },
    { title: 'Tests', detail: 'black-box test engineer from the failure matrix' },
    { title: 'Docs', detail: 'docs writer' },
    { title: 'QA', detail: 'suite, coverage ≥95% on changed lines, shortcut audit, flakes' },
  ],
}

const task = typeof args === 'string' ? args : args && args.task
if (!task) throw new Error('Pass the task as args (a string) or as args.task')
const opt = (typeof args === 'object' && args) || {}
const maxRounds = opt.rounds || 2
const base = opt.base || 'origin/master'
const MODEL = 'opus'
const PLANNER_MODEL = 'fable'

// ---- schemas ---------------------------------------------------------------
const strList = { type: 'array', items: { type: 'string' } }

const PLAN = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    stacks: { type: 'array', items: { type: 'string', enum: ['backend', 'frontend'] } },
    contract: { type: 'string' },
    brief_backend: { type: 'string' },
    brief_frontend: { type: 'string' },
    expected_failures: strList,
    specialists: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          role: { type: 'string', enum: ['consultant', 'reviewer'] },
          brief: { type: 'string' },
        },
        required: ['name', 'role', 'brief'],
      },
    },
    files: strList,
    risks: strList,
    assumptions: strList,
    needs_decision: strList,
  },
  required: ['summary', 'stacks', 'contract', 'brief_backend', 'brief_frontend', 'expected_failures', 'specialists', 'needs_decision'],
}

const DEV = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    files_changed: strList,
    tests_added: strList,
    checks_passed: { type: 'boolean' },
    deviations: strList,
    handoff: strList,
    rebuttals: strList,
  },
  required: ['summary', 'files_changed', 'checks_passed'],
}

const CROSSCHECK = {
  type: 'object',
  properties: {
    mismatches: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
        },
        required: ['file', 'summary', 'failure_scenario'],
      },
    },
  },
  required: ['mismatches'],
}

const CHALLENGE = {
  type: 'object',
  properties: {
    challenges: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          summary: { type: 'string' },
          why_it_matters: { type: 'string' },
          demand: { type: 'string' },
          proof_test: { type: 'string' },
        },
        required: ['file', 'severity', 'summary', 'why_it_matters', 'demand'],
      },
    },
    escalations: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          rebuttal: { type: 'string' },
          why_rejected: { type: 'string' },
        },
        required: ['summary', 'rebuttal', 'why_rejected'],
      },
    },
    accepted: strList,
    tests_added: strList,
  },
  required: ['challenges'],
}

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
          suggested_fix: { type: 'string' },
        },
        required: ['file', 'severity', 'summary', 'failure_scenario'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
  required: ['refuted', 'reason'],
}

const TESTS = {
  type: 'object',
  properties: {
    cases: strList,
    tests_added: strList,
    bugs: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
        },
        required: ['file', 'summary', 'failure_scenario'],
      },
    },
    untestable: strList,
    checks_passed: { type: 'boolean' },
  },
  required: ['cases', 'tests_added', 'bugs', 'checks_passed'],
}

const DOCS = {
  type: 'object',
  properties: { summary: { type: 'string' }, files_changed: strList, gaps: strList },
  required: ['summary', 'files_changed'],
}

const QA = {
  type: 'object',
  properties: {
    all_green: { type: 'boolean' },
    suites: {
      type: 'array',
      items: {
        type: 'object',
        properties: { name: { type: 'string' }, passed: { type: 'boolean' }, detail: { type: 'string' } },
        required: ['name', 'passed'],
      },
    },
    coverage: { type: 'string' },
    audit: { type: 'string' },
    flaky: strList,
    code_fixes_needed: strList,
  },
  required: ['all_green', 'suites'],
}

// ---- helpers ---------------------------------------------------------------
const show = (obj) => JSON.stringify(obj, null, 2)
const STACKS = {
  backend: { dev: 'dev-backend', challenger: 'challenger-backend', lenses: ['reviewer-python', 'reviewer-fastapi'] },
  frontend: { dev: 'dev-frontend', challenger: 'challenger-frontend', lenses: ['reviewer-typescript', 'reviewer-react', 'reviewer-ux'] },
}
const ownerOf = (file) => {
  if (!file) return 'dev-backend'
  if (file.startsWith('frontend/')) return 'dev-frontend'
  if (file.startsWith('docs/') || file === 'README.md' || file === 'CLAUDE.md' || file === 'CONTRIBUTING.md') return 'docs-writer'
  return 'dev-backend'
}
// Custom agent types load at session start. Until the next restart a new
// type is not registered; then a default agent reads its brief from
// .claude/agents/<type>.md and acts as that agent (tool restrictions from
// the frontmatter do not apply in that mode, the brief's rules still do).
async function run(type, prompt, opts) {
  try {
    return await agent(prompt, { model: MODEL, agentType: type, ...opts })
  } catch (e) {
    if (!String(e && e.message).includes('not found')) throw e
    log(`agent type '${type}' not registered in this session (restart Claude Code to load it); running from its brief file`)
    return agent(
      `First read the file .claude/agents/${type}.md and act exactly as the agent it describes, obeying every rule in it (including which files you may edit). Then do the task below.\n\n---\n\n${prompt}`,
      { model: MODEL, ...opts })
  }
}
// Ad-hoc specialists have no registered type: their planner-written brief
// becomes the head of the prompt.
const runAdhoc = (spec, prompt, opts) => agent(`${spec.brief}\n\n---\n\n${prompt}`, { model: MODEL, ...opts })
const dedupe = (items) => {
  const seen = new Set()
  return items.filter((f) => {
    const key = `${f.file}:${f.line || 0}:${(f.summary || '').slice(0, 40)}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

// ---- Plan ------------------------------------------------------------------
let plan
if (opt.plan === false) {
  if (!opt.stacks || !opt.stacks.length) throw new Error('args.plan=false needs args.stacks')
  plan = {
    summary: 'planning skipped', stacks: opt.stacks, contract: opt.contract || '',
    brief_backend: opt.stacks.includes('backend') ? task : '',
    brief_frontend: opt.stacks.includes('frontend') ? task : '',
    expected_failures: opt.expected_failures || [], specialists: [], needs_decision: [],
  }
  log('planning skipped (args.plan === false)')
} else {
  phase('Plan')
  plan = await run('planner',
    `Plan this task for SteamSelfGifter's dev team.\n\nTask:\n${task}\n\n` +
    (opt.decisions ? `The user answered your earlier questions; honour them and leave needs_decision empty unless something new comes up:\n${opt.decisions}\n\n` : '') +
    `Work on the current branch (uncommitted work is context, not something to undo). Do not edit files.`,
    { model: PLANNER_MODEL, effort: 'high', phase: 'Plan', schema: PLAN, label: 'plan' })
  if (!plan) throw new Error('Planner returned nothing')
  if (plan.needs_decision.length && !opt.proceed) {
    log(`planner has ${plan.needs_decision.length} open decision(s); stopping before the build`)
    return { task, plan, stopped_for_decisions: true, ready_to_commit: false }
  }
}
const stacks = plan.stacks.filter((s) => STACKS[s])
if (!stacks.length) throw new Error('Plan names no stack')
const briefs = { backend: plan.brief_backend, frontend: plan.brief_frontend }
const context = () =>
  `Task:\n${task}\n\nAPI contract:\n${plan.contract || '(single stack, no contract)'}\n\n` +
  `Expected failures:\n- ${(plan.expected_failures || []).join('\n- ')}`

// ---- Consult ---------------------------------------------------------------
const consultants = (plan.specialists || []).filter((s) => s.role === 'consultant')
const adhocReviewers = (plan.specialists || []).filter((s) => s.role === 'reviewer')
if (consultants.length) {
  phase('Consult')
  const notes = (await parallel(consultants.map((s) => () =>
    runAdhoc(s, `${context()}\n\nBriefs the devs will receive:\n${show(briefs)}\n\nWrite the guidance the devs need from your specialty for this task: constraints, pitfalls, exact formats, references. Do not edit files. Your final message is the guidance text.`,
      { phase: 'Consult', label: `consult:${s.name}` }).then((t) => (t ? `## Guidance from ${s.name}\n${t}` : null)),
  ))).filter(Boolean)
  for (const s of stacks) briefs[s] = `${briefs[s]}\n\n${notes.join('\n\n')}`
  log(`${notes.length} consultant note(s) appended to the briefs`)
}

// ---- Build -----------------------------------------------------------------
phase('Build')
const reports = {}
const built = await parallel(stacks.map((s) => () =>
  run(STACKS[s].dev, `${context()}\n\nYour brief:\n${briefs[s]}`, { phase: 'Build', schema: DEV, label: `build:${s}` })
    .then((r) => ({ stack: s, report: r }))))
for (const b of built.filter(Boolean)) reports[b.stack] = b.report
for (const s of stacks) if (!reports[s]) throw new Error(`${STACKS[s].dev} returned nothing`)
const history = [{ phase: 'build', reports: { ...reports } }]

const devFix = async (stack, prompt, label, phaseName) => {
  const r = await run(STACKS[stack].dev, prompt, { phase: phaseName, schema: DEV, label })
  if (r) reports[stack] = r
  return r
}
const fixPrompt = (stack, items, what) =>
  `${context()}\n\nYour brief:\n${briefs[stack]}\n\nYour last report:\n${show(reports[stack])}\n\n` +
  `${what}. Fix each one properly (no shortcuts), re-run your fast checks, and report again in the same shape. ` +
  `If one is wrong, say why under rebuttals; never silently skip one.\n\n${show(items)}`

// ---- Cross-check -----------------------------------------------------------
if (stacks.length === 2) {
  phase('Cross-check')
  const other = { backend: 'frontend', frontend: 'backend' }
  const checks = (await parallel(stacks.map((s) => () =>
    run(STACKS[s].dev,
      `${context()}\n\nThe ${other[s]} dev reports:\n${show(reports[other[s]])}\n\n` +
      `Verify the ${other[s]} side of the working tree against the contract: paths, methods, request and response shapes, status codes, error details, WebSocket messages. ` +
      `Read the code, not the report. Do not edit anything. Report every mismatch with file, line, summary and the failure it causes.`,
      { phase: 'Cross-check', schema: CROSSCHECK, label: `xcheck:${s}→${other[s]}` })
      .then((r) => (r ? r.mismatches.map((m) => ({ ...m, severity: 'medium', found_by: `${s}-dev` })) : [])),
  ))).filter(Boolean).flat()
  log(`cross-check: ${checks.length} contract mismatch(es)`)
  const byOwner = {}
  for (const m of checks) (byOwner[ownerOf(m.file)] ||= []).push(m)
  await parallel(Object.entries(byOwner).filter(([o]) => o !== 'docs-writer').map(([o, items]) => () => {
    const stack = o === 'dev-frontend' ? 'frontend' : 'backend'
    return devFix(stack, fixPrompt(stack, items, 'The other stack\'s dev found these contract mismatches on your side'), `xfix:${stack}`, 'Cross-check')
  }))
}

// ---- Challenge -------------------------------------------------------------
phase('Challenge')
const escalated = []
await parallel(stacks.map((s) => async () => {
  const ch = STACKS[s].challenger
  let round = 1
  let result = await run(ch,
    `${context()}\n\nThe ${s} dev's brief:\n${briefs[s]}\n\nThe dev's report:\n${show(reports[s])}\n\n` +
    `Round 1: challenge the ${s} side of the working tree (git diff, git status, read the code).`,
    { phase: 'Challenge', schema: CHALLENGE, label: `challenge:${s} r1` })
  while (result && result.challenges.length && round <= maxRounds) {
    log(`${s}: ${result.challenges.length} challenge(s) in round ${round}`)
    const answered = await devFix(s, fixPrompt(s, result.challenges, 'Your challenger raised these'), `answer:${s} r${round}`, 'Challenge')
    if (!answered) break
    if (round === maxRounds) {
      // No more rounds: unresolved rebuttals go straight to review as findings.
      for (const r of answered.rebuttals || []) escalated.push({ file: 'rebuttal', severity: 'medium', summary: r, failure_scenario: `Dev rebuttal not re-examined by the challenger (rounds exhausted): ${r}`, lens: `${s}-challenge` })
      break
    }
    round += 1
    result = await run(ch,
      `${context()}\n\nYour previous challenges:\n${show(result.challenges)}\n\nThe dev's response:\n${show(answered)}\n\n` +
      `Round ${round}: re-examine the working tree. Accept settled challenges, escalate rejected rebuttals, and only raise new challenges the fix created.`,
      { phase: 'Challenge', schema: CHALLENGE, label: `challenge:${s} r${round}` })
    if (result) {
      for (const e of result.escalations || []) escalated.push({ file: e.file || 'rebuttal', line: e.line, severity: 'medium', summary: e.summary, failure_scenario: `${e.why_rejected} (dev rebuttal: ${e.rebuttal})`, lens: `${s}-challenge` })
    }
  }
}))
log(`challenge phase done: ${escalated.length} escalation(s) carried into review`)
history.push({ phase: 'challenge', reports: { ...reports }, escalations: escalated })

// ---- Review / Verify / Fix rounds -----------------------------------------
const allReports = () => `Dev reports:\n${show(reports)}`
const reviewPrompt = () =>
  `${context()}\n\n${allReports()}\n\nReview the uncommitted working-tree changes: run \`git diff ${base}\` and \`git status\`, and read any untracked files the reports list.`
const refutePrompt = (f) =>
  `A reviewer (${f.lens} lens) reported this finding on the uncommitted working-tree changes:\n${show(f)}\n\n${context()}\n\n` +
  `Try to refute it. Read the code at that location and the callers. The finding stands only if the failure scenario is reachable in practice through this change. ` +
  `Set refuted=true if it cannot happen, is already handled, or is outside what the task changed. Default to refuted=true if unsure. Do not edit files.`

const lensesFor = () => {
  const core = ['reviewer-correctness', 'reviewer-security', 'reviewer-conventions']
  const stackLenses = stacks.flatMap((s) => STACKS[s].lenses)
  return [...core, ...stackLenses]
}

let reviewClean = false
let lastConfirmed = []
let carried = escalated
for (let round = 1; round <= maxRounds; round++) {
  phase('Review')
  const raw = (await parallel([
    ...lensesFor().map((type) => () =>
      run(type, reviewPrompt(), { phase: 'Review', schema: FINDINGS, label: `review:${type.replace('reviewer-', '')} r${round}` })
        .then((res) => (res ? res.findings.map((f) => ({ ...f, lens: type.replace('reviewer-', '') })) : []))),
    ...adhocReviewers.map((spec) => () =>
      runAdhoc(spec, `${reviewPrompt()}\n\nReport findings only with a concrete failure scenario; an empty list is valid.`,
        { phase: 'Review', schema: FINDINGS, label: `review:${spec.name} r${round}` })
        .then((res) => (res ? res.findings.map((f) => ({ ...f, lens: spec.name })) : []))),
  ])).filter(Boolean).flat()
  const fresh = dedupe([...carried, ...raw])
  carried = []
  log(`review round ${round}: ${raw.length} findings + ${escalated.length ? 'escalations' : '0 escalations'}, ${fresh.length} after dedup`)
  if (!fresh.length) { reviewClean = true; lastConfirmed = []; break }

  phase('Verify')
  const judged = (await parallel(fresh.map((f) => () =>
    agent(refutePrompt(f), { model: MODEL, effort: 'high', phase: 'Verify', schema: VERDICT, label: `verify:${(f.file || '').split('/').pop()}` })
      .then((v) => ({ ...f, refuted: v ? v.refuted : true, verdict_reason: v ? v.reason : 'refuter failed' })),
  ))).filter(Boolean)
  lastConfirmed = judged.filter((f) => !f.refuted)
  log(`review round ${round}: ${lastConfirmed.length}/${fresh.length} findings survived refutation`)
  if (!lastConfirmed.length) { reviewClean = true; break }

  phase('Fix')
  const byOwner = {}
  for (const f of lastConfirmed) (byOwner[ownerOf(f.file)] ||= []).push(f)
  await parallel(Object.entries(byOwner).map(([owner, items]) => () => {
    if (owner === 'docs-writer') {
      return run('docs-writer', `${context()}\n\nReviewers confirmed these documentation findings; fix them.\n\n${show(items)}`, { phase: 'Fix', schema: DOCS, label: `fix:docs r${round}` })
    }
    const stack = owner === 'dev-frontend' ? 'frontend' : 'backend'
    return devFix(stack, fixPrompt(stack, items, 'Independent review confirmed these findings'), `fix:${stack} r${round}`, 'Fix')
  }))
  history.push({ phase: `fix r${round}`, reports: { ...reports }, findings: lastConfirmed })
  if (round === maxRounds) log(`review rounds exhausted after ${maxRounds}; the last fixes were not re-reviewed`)
}

// ---- Tests (black-box) -----------------------------------------------------
phase('Tests')
const tests = await run('test-engineer',
  `${context()}\n\n${allReports()}\n\nDerive the case list from the task, the contract and the expected failures BEFORE reading the implementation, then cover every gap. Compare against ${base}.`,
  { phase: 'Tests', schema: TESTS, label: 'test-engineer' })
if (tests && tests.bugs.length) {
  log(`test engineer proved ${tests.bugs.length} bug(s); routing to the devs`)
  const byOwner = {}
  for (const b of tests.bugs) (byOwner[ownerOf(b.file)] ||= []).push({ ...b, severity: 'high' })
  await parallel(Object.entries(byOwner).filter(([o]) => o !== 'docs-writer').map(([o, items]) => () => {
    const stack = o === 'dev-frontend' ? 'frontend' : 'backend'
    return devFix(stack, fixPrompt(stack, items, 'The test engineer wrote tests that fail and believes these are defects. Make the tests pass by fixing the code; never weaken a test'), `bugfix:${stack}`, 'Tests')
  }))
}

// ---- Docs ------------------------------------------------------------------
phase('Docs')
const docs = await run('docs-writer', `Bring the documentation in line with this change.\n\n${context()}\n\n${allReports()}`,
  { phase: 'Docs', schema: DOCS, label: 'docs' })

// ---- QA --------------------------------------------------------------------
phase('QA')
const qaPrompt = () => `Verify this change end to end. Base ref for coverage and the shortcut audit: ${base}.\n\n${context()}\n\n${allReports()}`
let qa = await run('qa', qaPrompt(), { phase: 'QA', schema: QA, label: 'qa' })
if (qa && !qa.all_green) {
  const red = qa.suites.filter((s) => !s.passed).map((s) => s.name)
  log(`QA red (${red.join(', ') || 'gates'}); one repair round`)
  const items = [
    ...(qa.code_fixes_needed || []).map((c) => ({ file: 'see detail', severity: 'high', summary: c, failure_scenario: c })),
    ...(qa.flaky || []).map((t) => ({ file: 'see detail', severity: 'medium', summary: `flaky: ${t}`, failure_scenario: 'failed at least once in three runs' })),
  ]
  const extra = `QA report:\n${show(qa)}`
  await parallel(stacks.map((s) => () =>
    devFix(s, fixPrompt(s, items, `QA is red. Fix what is yours in the ${s} stack (application code or a wrong test, never a weakened test); uncovered lines need tests`) + `\n\n${extra}`, `qa-fix:${s}`, 'QA')))
  qa = await run('qa', qaPrompt(), { phase: 'QA', schema: QA, label: 'qa rerun' })
}

return {
  task,
  plan: { summary: plan.summary, stacks, contract: plan.contract, expected_failures: plan.expected_failures, specialists: plan.specialists, risks: plan.risks, assumptions: plan.assumptions },
  review_clean: reviewClean,
  findings_fixed_but_not_re_reviewed: reviewClean ? [] : lastConfirmed,
  tests,
  docs,
  qa,
  history,
  ready_to_commit: Boolean(reviewClean && qa && qa.all_green),
}
