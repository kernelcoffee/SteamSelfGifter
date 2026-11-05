import { useId, useState } from 'react';
import { Save, TestTube, AlertCircle, Eye, EyeOff, HelpCircle, ExternalLink, Info } from 'lucide-react';
import { Card, Button, Input, Toggle, Loading, PriorityList } from '@/components/common';
import { GenreListsEditor } from '@/components/features/GenreListsEditor';
import { AutojoinPreviewLine, type PreviewStatus } from '@/components/features/AutojoinPreviewLine';
import {
  useSettings,
  useUpdateSettings,
  useTestSession,
  useAutojoinRegistry,
  useAutojoinPreview,
  useDebouncedValue,
} from '@/hooks';
import { showSuccess, showError } from '@/stores/uiStore';
import type {
  AutojoinPriorityItem,
  AutojoinRegistry,
  PolicyPreviewRequest,
  RegistryParam,
  Settings as SettingsType,
} from '@/types';
import { registryLabels, thresholdParam, withThreshold } from '@/utils/autojoinPriorities';
import {
  checkGenreDraft,
  genreDraftSaveBlockedReason,
  type GenreLimits,
  type GenreListName,
  type GenreLists,
} from '@/utils/genreLists';
import { parseBoundedInt } from '@/utils/numbers';

/** Delay between the last edit and the preview request. */
const PREVIEW_DEBOUNCE_MS = 400;

/** Number fields edited as text, so a cleared field is never sent as 0. */
type DraftField =
  | 'autojoin_min_price'
  | 'autojoin_min_score'
  | 'autojoin_min_reviews'
  | 'autojoin_max_game_age'
  | 'autojoin_start_at'
  | 'autojoin_stop_at'
  | 'max_entries_per_cycle'
  | 'entry_delay_min'
  | 'entry_delay_max'
  | 'scan_interval_minutes'
  | 'max_scan_pages'
  | 'log_retention_days';

/** Number fields that can be turned off (sent as null). */
type OptionalField = 'autojoin_min_score' | 'autojoin_min_reviews' | 'autojoin_max_game_age';

function isOptional(field: DraftField): field is OptionalField {
  return (
    field === 'autojoin_min_score' ||
    field === 'autojoin_min_reviews' ||
    field === 'autojoin_max_game_age'
  );
}

/** Build a record over every draft field. */
function mapDraftFields<T>(fn: (field: DraftField) => T): Record<DraftField, T> {
  return {
    autojoin_min_price: fn('autojoin_min_price'),
    autojoin_min_score: fn('autojoin_min_score'),
    autojoin_min_reviews: fn('autojoin_min_reviews'),
    autojoin_max_game_age: fn('autojoin_max_game_age'),
    autojoin_start_at: fn('autojoin_start_at'),
    autojoin_stop_at: fn('autojoin_stop_at'),
    max_entries_per_cycle: fn('max_entries_per_cycle'),
    entry_delay_min: fn('entry_delay_min'),
    entry_delay_max: fn('entry_delay_max'),
    scan_interval_minutes: fn('scan_interval_minutes'),
    max_scan_pages: fn('max_scan_pages'),
    log_retention_days: fn('log_retention_days'),
  };
}

// Bounds mirror the settings schema (SettingsUpdate field constraints).
const DRAFT_RULES: Record<DraftField, { min: number; max?: number; error: string }> = {
  autojoin_min_price: { min: 0, error: 'Enter a minimum price of 0 points or more' },
  autojoin_min_score: {
    min: 0,
    max: 10,
    error: 'Enter a minimum review score from 0 to 10, or choose No minimum',
  },
  autojoin_min_reviews: {
    min: 0,
    error: 'Enter a minimum review count of 0 or more, or choose No minimum',
  },
  autojoin_max_game_age: {
    min: 1,
    error: 'Enter a maximum age of 1 year or more, or choose No limit',
  },
  autojoin_start_at: { min: 0, error: 'Enter a start threshold of 0 points or more' },
  autojoin_stop_at: { min: 0, error: 'Enter a stop threshold of 0 points or more' },
  max_entries_per_cycle: { min: 1, error: 'Enter a per cycle cap of 1 or more' },
  entry_delay_min: { min: 0, error: 'Enter a minimum delay of 0 seconds or more' },
  entry_delay_max: { min: 0, error: 'Enter a maximum delay of 0 seconds or more' },
  scan_interval_minutes: { min: 1, error: 'Enter a scan interval of 1 minute or more' },
  max_scan_pages: { min: 1, error: 'Enter a number of scan pages of 1 or more' },
  log_retention_days: { min: 0, error: 'Enter a log retention of 0 days or more' },
};

// Draft restored when an optional filter is turned back on with no saved value
// (the backend's defaults).
const OPTIONAL_DEFAULTS: Record<OptionalField, string> = {
  autojoin_min_score: '7',
  autojoin_min_reviews: '1000',
  autojoin_max_game_age: '',
};

function initialDrafts(settings: SettingsType): Record<DraftField, string> {
  return mapDraftFields((field) => {
    const value = settings[field];
    return value === null ? '' : String(value);
  });
}

function policyFromSettings(settings: SettingsType): PolicyPreviewRequest {
  return {
    autojoin_min_price: settings.autojoin_min_price,
    autojoin_min_score: settings.autojoin_min_score,
    autojoin_min_reviews: settings.autojoin_min_reviews,
    autojoin_max_game_age: settings.autojoin_max_game_age,
    excluded_genres: settings.excluded_genres,
    included_genres: settings.included_genres,
    autojoin_priorities: settings.autojoin_priorities,
  };
}

function joinWith(names: string[], word: 'and' | 'or'): string {
  if (names.length <= 1) return names.join('');
  return `${names.slice(0, -1).join(', ')} ${word} ${names[names.length - 1]}`;
}

function RegistryError({ message }: { message: string }) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
      <Card>
        <div className="flex items-start gap-3 text-red-600 dark:text-red-400">
          <AlertCircle size={24} className="shrink-0" aria-hidden="true" />
          <div className="space-y-1">
            <p>
              Could not load the auto-join registry (GET /giveaways/registry). Reload the page; if
              it keeps failing check the backend logs.
            </p>
            <p className="text-sm">{message}</p>
          </div>
        </div>
      </Card>
    </div>
  );
}

/**
 * Settings page
 * Configure credentials, the auto-join policy (filters, priority order,
 * budget), safety and the scheduler. The policy rules come from the backend
 * registry, so the form waits for both settings and registry.
 */
export function Settings() {
  const { data: settings, isLoading, error, refetch } = useSettings();
  const registry = useAutojoinRegistry();

  if (isLoading || registry.isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <Loading text="Loading settings..." />
      </div>
    );
  }

  if (error || !settings) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <Card>
          <div className="flex flex-wrap items-center gap-3">
            <AlertCircle size={24} className="shrink-0 text-red-500" aria-hidden="true" />
            <span role="alert" className="min-w-0 flex-1 text-red-500">
              Failed to load settings: {error?.message ?? 'no data returned'}
            </span>
            <Button type="button" variant="secondary" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (registry.error || !registry.data) {
    return <RegistryError message={registry.error?.message ?? 'No registry data'} />;
  }

  const threshold = thresholdParam(registry.data.priority_types);
  if (!threshold) {
    return <RegistryError message="The registry has no ending soon threshold bounds" />;
  }

  // Remount the form whenever the server state changes (e.g. after a save's
  // refetch) so it re-initializes from fresh data without effect-driven state.
  return (
    <SettingsForm
      key={settings.updated_at}
      settings={settings}
      registry={registry.data}
      threshold={threshold}
    />
  );
}

interface FormFields {
  phpsessid: string;
  user_agent: string;
  automation_enabled: boolean;
  autojoin_enabled: boolean;
  safety_check_enabled: boolean;
  auto_hide_unsafe: boolean;
  autojoin_priorities: AutojoinPriorityItem[];
  excluded_genres: string[];
  included_genres: string[];
}

function SettingsForm({
  settings,
  registry,
  threshold,
}: {
  settings: SettingsType;
  registry: AutojoinRegistry;
  threshold: RegistryParam;
}) {
  const updateSettings = useUpdateSettings();
  const testSession = useTestSession();
  const reasonId = useId();

  const [fields, setFields] = useState<FormFields>(() => ({
    phpsessid: settings.phpsessid ?? '',
    user_agent: settings.user_agent,
    automation_enabled: settings.automation_enabled,
    autojoin_enabled: settings.autojoin_enabled,
    safety_check_enabled: settings.safety_check_enabled,
    auto_hide_unsafe: settings.auto_hide_unsafe,
    autojoin_priorities: settings.autojoin_priorities,
    excluded_genres: settings.excluded_genres,
    included_genres: settings.included_genres,
  }));
  const [drafts, setDrafts] = useState(() => initialDrafts(settings));
  const [off, setOff] = useState<Record<OptionalField, boolean>>(() => ({
    autojoin_min_score: settings.autojoin_min_score === null,
    autojoin_min_reviews: settings.autojoin_min_reviews === null,
    autojoin_max_game_age: settings.autojoin_max_game_age === null,
  }));
  const savedThreshold = settings.autojoin_priorities.find(
    (item): item is Extract<AutojoinPriorityItem, { type: 'ending_soon' }> =>
      item.type === 'ending_soon',
  )?.threshold_minutes;
  // Raw text of the threshold field: lets the user clear it and type freely.
  const [thresholdText, setThresholdText] = useState(() => String(savedThreshold ?? threshold.default));
  // Text typed in the "Add a genre" field but not added yet. It lives here,
  // not in the editor, so an unconfirmed genre blocks saving instead of
  // being dropped without a word when the form is saved.
  const [genreDraft, setGenreDraft] = useState('');
  const [genreDraftTarget, setGenreDraftTarget] = useState<GenreListName>('excluded');
  // Edits to any field. The genre draft is not a field, so it counts as a
  // change only while it holds text (see hasChanges).
  const [formEdited, setFormEdited] = useState(false);
  const [showPhpsessid, setShowPhpsessid] = useState(false);

  const genreLimits: GenreLimits = {
    maxItems: registry.limits.genre_max_items,
    maxLength: registry.limits.genre_max_length,
  };
  const labels = registryLabels(registry);
  const endingSoonLabel =
    registry.priority_types.find((t) => t.type === 'ending_soon')?.label ?? 'Ending soon';
  const exemptLabels = registry.priority_types
    .filter((t) => t.exempt_from_filters)
    .map((t) => t.label);

  // --- Parsed values and inline errors -------------------------------------
  const parsed = mapDraftFields((field) => {
    const rule = DRAFT_RULES[field];
    return parseBoundedInt(drafts[field], rule.min, rule.max);
  });
  const isOff = (field: DraftField): boolean => isOptional(field) && off[field];
  const fieldError = (field: DraftField): string | undefined =>
    !isOff(field) && parsed[field] === null ? DRAFT_RULES[field].error : undefined;

  const stopError =
    fieldError('autojoin_stop_at') ??
    (parsed.autojoin_stop_at !== null &&
    parsed.autojoin_start_at !== null &&
    parsed.autojoin_stop_at > parsed.autojoin_start_at
      ? 'Stop at must not be above Start at'
      : undefined);
  const delayMaxError =
    fieldError('entry_delay_max') ??
    (parsed.entry_delay_max !== null &&
    parsed.entry_delay_min !== null &&
    parsed.entry_delay_max < parsed.entry_delay_min
      ? 'Max delay must not be below Min delay'
      : undefined);

  const hasEndingSoon = fields.autojoin_priorities.some((item) => item.type === 'ending_soon');
  const parsedThreshold = parseBoundedInt(thresholdText, threshold.min, threshold.max);
  const thresholdError =
    hasEndingSoon && parsedThreshold === null
      ? `Must be between ${threshold.min} and ${threshold.max} minutes`
      : undefined;
  const thresholdReason = thresholdError
    ? `Enter an ${endingSoonLabel.toLowerCase()} threshold between ${threshold.min} and ${threshold.max} minutes to save`
    : undefined;

  const genreTargetList = genreDraftTarget === 'excluded' ? fields.excluded_genres : fields.included_genres;
  const genreDraftState = checkGenreDraft(genreDraft, genreTargetList, genreLimits);
  const genreReason = genreDraftSaveBlockedReason(genreDraftState, genreDraftTarget);

  // Reasons in page order; the first one is shown next to the Save buttons.
  const policyReasons = [
    fieldError('autojoin_min_price'),
    genreReason,
    fieldError('autojoin_min_score'),
    fieldError('autojoin_min_reviews'),
    fieldError('autojoin_max_game_age'),
    thresholdReason,
  ].filter((reason): reason is string => reason !== undefined);
  const otherReasons = [
    fieldError('autojoin_start_at'),
    stopError,
    fieldError('max_entries_per_cycle'),
    fieldError('entry_delay_min'),
    delayMaxError,
    fieldError('scan_interval_minutes'),
    fieldError('max_scan_pages'),
    fieldError('log_retention_days'),
  ].filter((reason): reason is string => reason !== undefined);
  const saveBlockedReason = [...policyReasons, ...otherReasons][0];
  const policyBlockedReason = policyReasons[0];
  const isValid = saveBlockedReason === undefined;
  const hasChanges = formEdited || genreDraftState.status !== 'empty';

  // --- Live preview of the edited policy -----------------------------------
  const optionalValue = (field: OptionalField) => (off[field] ? null : parsed[field]);
  const minPrice = parsed.autojoin_min_price;
  const minScore = optionalValue('autojoin_min_score');
  const minReviews = optionalValue('autojoin_min_reviews');
  const maxAge = optionalValue('autojoin_max_game_age');
  const { autojoin_priorities: priorities, excluded_genres: excluded, included_genres: included } = fields;
  // The debounce compares by content, so a new object with the same values
  // neither restarts the timer nor changes the query key.
  const policy: PolicyPreviewRequest | null =
    policyBlockedReason !== undefined || minPrice === null
      ? null
      : {
          autojoin_min_price: minPrice,
          autojoin_min_score: minScore,
          autojoin_min_reviews: minReviews,
          autojoin_max_game_age: maxAge,
          excluded_genres: excluded,
          included_genres: included,
          autojoin_priorities: withThreshold(priorities, parsedThreshold ?? threshold.default),
        };
  const savedPolicy = policyFromSettings(settings);
  const debouncedPolicy = useDebouncedValue(policy, PREVIEW_DEBOUNCE_MS);
  const preview = useAutojoinPreview(debouncedPolicy ?? savedPolicy, policy !== null && debouncedPolicy !== null);
  // Same key as the first preview of an unedited form, so no extra request.
  const savedPreview = useAutojoinPreview(savedPolicy, true);

  // While a policy that was invalid waits for its first debounced request,
  // the hook still points at the saved policy; its numbers are not shown.
  const previewData = debouncedPolicy !== null ? preview.data : undefined;
  let previewStatus: PreviewStatus;
  if (policy === null) previewStatus = 'paused';
  else if (preview.isError && !preview.isFetching) previewStatus = 'error';
  else if (previewData) previewStatus = 'ready';
  else previewStatus = 'loading';
  const previewIsStale =
    preview.isPlaceholderData ||
    preview.isFetching ||
    JSON.stringify(policy) !== JSON.stringify(debouncedPolicy);

  const previewLine = (live: boolean) => (
    <AutojoinPreviewLine
      status={previewStatus}
      pausedReason={policyBlockedReason}
      error={preview.error?.message}
      onRetry={() => {
        void preview.refetch();
      }}
      data={previewData}
      savedCount={savedPreview.data?.count}
      labels={labels}
      isStale={previewIsStale}
      live={live}
    />
  );

  // Exempt types the saved list had and the edited list lost.
  const lostExemptions = registry.priority_types.filter(
    (t) =>
      t.exempt_from_filters &&
      settings.autojoin_priorities.some((item) => item.type === t.type) &&
      !fields.autojoin_priorities.some((item) => item.type === t.type),
  );

  // --- Handlers ------------------------------------------------------------
  const setField = <K extends keyof FormFields>(field: K, value: FormFields[K]) => {
    setFields((prev) => ({ ...prev, [field]: value }));
    setFormEdited(true);
  };

  const setDraft = (field: DraftField, text: string) => {
    setDrafts((prev) => ({ ...prev, [field]: text }));
    setFormEdited(true);
  };

  const setOptionalOff = (field: OptionalField, value: boolean) => {
    setOff((prev) => ({ ...prev, [field]: value }));
    if (!value && drafts[field].trim() === '') {
      const saved = settings[field];
      setDrafts((prev) => ({ ...prev, [field]: saved === null ? OPTIONAL_DEFAULTS[field] : String(saved) }));
    }
    setFormEdited(true);
  };

  const handleGenreListsChange = (lists: GenreLists) => {
    setFields((prev) => ({ ...prev, excluded_genres: lists.excluded, included_genres: lists.included }));
    setFormEdited(true);
  };

  const handleThresholdChange = (text: string) => {
    setThresholdText(text);
    setFormEdited(true);
  };

  const buildPayload = (): Partial<SettingsType> | null => {
    const p = parsed;
    if (
      !isValid ||
      p.autojoin_min_price === null ||
      p.autojoin_start_at === null ||
      p.autojoin_stop_at === null ||
      p.max_entries_per_cycle === null ||
      p.entry_delay_min === null ||
      p.entry_delay_max === null ||
      p.scan_interval_minutes === null ||
      p.max_scan_pages === null ||
      p.log_retention_days === null
    ) {
      return null;
    }
    return {
      phpsessid: fields.phpsessid,
      user_agent: fields.user_agent,
      automation_enabled: fields.automation_enabled,
      autojoin_enabled: fields.autojoin_enabled,
      safety_check_enabled: fields.safety_check_enabled,
      auto_hide_unsafe: fields.auto_hide_unsafe,
      autojoin_min_price: p.autojoin_min_price,
      autojoin_min_score: minScore,
      autojoin_min_reviews: minReviews,
      autojoin_max_game_age: maxAge,
      excluded_genres: fields.excluded_genres,
      included_genres: fields.included_genres,
      autojoin_priorities: withThreshold(fields.autojoin_priorities, parsedThreshold ?? threshold.default),
      autojoin_start_at: p.autojoin_start_at,
      autojoin_stop_at: p.autojoin_stop_at,
      max_entries_per_cycle: p.max_entries_per_cycle,
      entry_delay_min: p.entry_delay_min,
      entry_delay_max: p.entry_delay_max,
      scan_interval_minutes: p.scan_interval_minutes,
      max_scan_pages: p.max_scan_pages,
      log_retention_days: p.log_retention_days,
    };
  };

  const handleSave = async () => {
    const payload = buildPayload();
    if (payload === null) return;
    try {
      await updateSettings.mutateAsync(payload);
      showSuccess('Settings saved. Auto-join uses them from the next cycle.');
      setFormEdited(false);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to save settings');
    }
  };

  const handleTestSession = async () => {
    try {
      const result = await testSession.mutateAsync();
      if (result.valid) {
        showSuccess(`Session valid! User: ${result.username}, Points: ${result.points}`);
      } else {
        showError(result.error || 'Session is invalid. Please update your PHPSESSID.');
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to test session');
    }
  };

  const numberInput = (field: DraftField, label: string, helperText: string, error?: string) => (
    <Input
      label={label}
      type="number"
      inputMode="numeric"
      min={DRAFT_RULES[field].min}
      max={DRAFT_RULES[field].max}
      required
      value={drafts[field]}
      onChange={(e) => setDraft(field, e.target.value)}
      helperText={helperText}
      error={error ?? fieldError(field)}
    />
  );

  const optionalInput = (
    field: OptionalField,
    label: string,
    offText: string,
    offAriaLabel: string,
    onHelper: string,
    offHelper: string,
  ) => (
    <div className="space-y-2">
      <Input
        label={label}
        type="number"
        inputMode="numeric"
        min={DRAFT_RULES[field].min}
        max={DRAFT_RULES[field].max}
        disabled={off[field]}
        placeholder={off[field] ? offText : undefined}
        value={off[field] ? '' : drafts[field]}
        onChange={(e) => setDraft(field, e.target.value)}
        helperText={off[field] ? offHelper : onHelper}
        error={fieldError(field)}
      />
      <label className="flex flex-wrap items-center gap-3 text-sm text-gray-700 dark:text-gray-300">
        <input
          id={`${field}-off`}
          type="checkbox"
          aria-label={offAriaLabel}
          checked={off[field]}
          onChange={(e) => setOptionalOff(field, e.target.checked)}
          className="rounded border-gray-300 dark:border-gray-600 dark:bg-gray-800 text-primary-light"
        />
        <span>{offText}</span>
      </label>
    </div>
  );

  const autojoinOffNotice = !fields.autojoin_enabled && (
    <p className="flex items-start gap-2 rounded-lg bg-yellow-50 dark:bg-yellow-900/20 p-3 text-sm text-yellow-800 dark:text-yellow-200">
      <Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      Auto-join is off: these rules are used once you turn it on in Automation.
    </p>
  );

  const saveButton = (describe: boolean) => (
    <Button
      onClick={handleSave}
      isLoading={updateSettings.isPending}
      disabled={!hasChanges || !isValid}
      aria-describedby={describe && hasChanges ? reasonId : undefined}
      icon={Save}
      className="shrink-0"
    >
      Save Changes
    </Button>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        {saveButton(true)}
      </div>

      {/* First-time Setup Guide */}
      {!settings.phpsessid && (
        <Card>
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-4">
            <div className="flex items-start gap-3">
              <HelpCircle className="text-blue-500 shrink-0 mt-0.5" size={20} />
              <div>
                <h3 className="font-semibold text-blue-800 dark:text-blue-200 mb-2">
                  Getting Started
                </h3>
                <p className="text-sm text-blue-700 dark:text-blue-300 mb-3">
                  To use SteamSelfGifter, you need to provide your SteamGifts session cookie (PHPSESSID).
                  Follow these steps:
                </p>
                <ol className="text-sm text-blue-700 dark:text-blue-300 list-decimal list-inside space-y-2">
                  <li>
                    <a
                      href="https://www.steamgifts.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline hover:text-blue-800 dark:hover:text-blue-100 inline-flex items-center gap-1"
                    >
                      Log in to SteamGifts.com <ExternalLink size={12} />
                    </a>
                  </li>
                  <li>Open your browser's Developer Tools (F12 or right-click → Inspect)</li>
                  <li>Go to the <strong>Application</strong> tab (Chrome) or <strong>Storage</strong> tab (Firefox)</li>
                  <li>Find <strong>Cookies</strong> → <strong>https://www.steamgifts.com</strong></li>
                  <li>Copy the value of the <strong>PHPSESSID</strong> cookie</li>
                  <li>Paste it in the field below, click <strong>Save Changes</strong>, then <strong>Test Session</strong> to verify</li>
                </ol>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Credentials Section */}
      <Card title="SteamGifts Credentials">
        <div className="space-y-4">
          <div className="relative">
            <Input
              label="PHPSESSID"
              type={showPhpsessid ? 'text' : 'password'}
              value={fields.phpsessid}
              onChange={(e) => setField('phpsessid', e.target.value)}
              helperText="Your SteamGifts session cookie. Get this from browser DevTools."
            />
            <button
              type="button"
              onClick={() => setShowPhpsessid(!showPhpsessid)}
              className="absolute right-3 top-8 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              aria-label={showPhpsessid ? 'Hide PHPSESSID' : 'Show PHPSESSID'}
            >
              {showPhpsessid ? <EyeOff size={20} /> : <Eye size={20} />}
            </button>
          </div>
          <Input
            label="User Agent"
            value={fields.user_agent}
            onChange={(e) => setField('user_agent', e.target.value)}
            helperText="Browser user agent string for requests."
          />
          <Button
            onClick={handleTestSession}
            isLoading={testSession.isPending}
            variant="secondary"
            icon={TestTube}
          >
            Test Session
          </Button>
        </div>
      </Card>

      {/* Automation Section */}
      <Card title="Automation">
        <div className="space-y-4">
          <Toggle
            label="Enable Automation"
            description="Allow the scheduler to run automatic scans and entries"
            checked={fields.automation_enabled}
            onChange={(checked) => setField('automation_enabled', checked)}
          />
          <Toggle
            label="Enable Auto-Join"
            description="Automatically enter giveaways that pass your filters, in your priority order"
            checked={fields.autojoin_enabled}
            onChange={(checked) => setField('autojoin_enabled', checked)}
          />
        </div>
      </Card>

      {/* Filters: what auto-join skips */}
      <Card title="Filters: what auto-join skips">
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Auto-join skips any giveaway that fails one of these.
            {exemptLabels.length > 0 &&
              ` ${joinWith(exemptLabels, 'and')} giveaways skip them only while ${joinWith(exemptLabels, 'or')} is in your priority order.`}
          </p>
          {autojoinOffNotice}
          <div className="max-w-sm">
            {numberInput('autojoin_min_price', 'Minimum price (points)', '0 enters any price.')}
          </div>
          <GenreListsEditor
            excluded={fields.excluded_genres}
            included={fields.included_genres}
            onChange={handleGenreListsChange}
            draft={genreDraft}
            onDraftChange={setGenreDraft}
            draftTarget={genreDraftTarget}
            onDraftTargetChange={setGenreDraftTarget}
            draftState={genreDraftState}
            limits={genreLimits}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {optionalInput(
              'autojoin_min_score',
              'Minimum review score',
              'No minimum',
              'No minimum review score',
              '0 to 10. 0 still needs Steam data; choose No minimum to turn the filter off.',
              'Off: review score is not checked',
            )}
            {optionalInput(
              'autojoin_min_reviews',
              'Minimum review count',
              'No minimum',
              'No minimum review count',
              '0 or more. 0 still needs Steam data; choose No minimum to turn the filter off.',
              'Off: review count is not checked',
            )}
            {optionalInput(
              'autojoin_max_game_age',
              'Maximum game age (years)',
              'No limit',
              'No age limit',
              'Only enter games released within this many years.',
              'Off: game age is not checked',
            )}
          </div>
          <p className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300">
            <Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>
              Giveaways without cached Steam data are skipped while a minimum score, minimum reviews
              or maximum age is set; they are checked again each cycle. The excluded-genres filter
              lets them through; a non-empty included-genres list skips them.
            </span>
          </p>
          {previewLine(true)}
        </div>
      </Card>

      {/* Priority order */}
      <Card title="Priority order">
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Matching giveaways are entered top to bottom while points last; everything else follows,
            highest price first. Gates (ended, hidden, already entered, unsafe) are never skipped.
          </p>
          {autojoinOffNotice}
          <PriorityList
            items={fields.autojoin_priorities}
            onChange={(items) => setField('autojoin_priorities', items)}
            types={registry.priority_types}
            maxItems={registry.limits.max_priority_items}
            threshold={threshold}
            thresholdText={thresholdText}
            onThresholdTextChange={handleThresholdChange}
            thresholdError={thresholdError}
          />
          {previewLine(false)}
        </div>
      </Card>

      {/* Points budget and pacing */}
      <Card title="Points budget and pacing">
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            When auto-join starts and stops spending points, and how fast it enters.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {numberInput(
              'autojoin_start_at',
              'Start at (points)',
              'Only auto-join when you have at least this many points',
            )}
            {numberInput(
              'autojoin_stop_at',
              'Stop at (points)',
              'Skip a giveaway whose price would take your points below this',
              stopError,
            )}
            {numberInput(
              'max_entries_per_cycle',
              'Per cycle cap',
              'At most this many entry attempts per cycle. Giveaways skipped for points do not use a slot.',
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {numberInput('entry_delay_min', 'Min entry delay (seconds)', 'Minimum delay between entries')}
            {numberInput(
              'entry_delay_max',
              'Max entry delay (seconds)',
              'Maximum delay between entries',
              delayMaxError,
            )}
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Random delays between these values help avoid rate limiting and detection.
          </p>
        </div>
      </Card>

      {/* Safety Settings */}
      <Card title="Safety">
        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Runs before every entry, wishlist and DLC included.
          </p>
          <Toggle
            label="Enable Trap Detection"
            description="Scan each giveaway's description and comments for trap language (e.g., 'do not enter', 'bot trap', 'you will be banned') before auto-entering"
            checked={fields.safety_check_enabled}
            onChange={(checked) => setField('safety_check_enabled', checked)}
          />
          <Toggle
            label="Hide unsafe giveaways on SteamGifts"
            description="Off: detected traps are hidden in this app only and never hidden on SteamGifts"
            checked={fields.auto_hide_unsafe}
            onChange={(checked) => setField('auto_hide_unsafe', checked)}
          />
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Unchecked giveaways are scored by a background sweep each cycle. Outright traps are
            hidden; borderline scores (50&ndash;84) are skipped by auto-entry but stay visible with a
            Borderline badge so you can review them and re-check manually.
          </p>
        </div>
      </Card>

      {/* Scheduler Settings */}
      <Card title="Scheduler">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {numberInput('scan_interval_minutes', 'Scan interval (minutes)', 'How often to scan for new giveaways')}
          {numberInput('max_scan_pages', 'Max scan pages', 'Maximum pages to scan per cycle')}
          {numberInput(
            'log_retention_days',
            'Log retention (days)',
            'Activity logs older than this are pruned (0 = keep forever)',
          )}
        </div>
      </Card>

      {/* Sticky save bar */}
      {hasChanges && (
        <div className="sticky bottom-0 z-20 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/40 p-4 shadow-lg">
          <div className="min-w-0 flex-1 space-y-1 text-sm text-yellow-800 dark:text-yellow-200">
            <p>Saving changes what auto-join enters from the next cycle.</p>
            {lostExemptions.map((t) => (
              <p key={t.type}>{t.label} giveaways will obey your filters after saving.</p>
            ))}
            <p id={reasonId} className="flex items-start gap-2 font-medium">
              <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span>{saveBlockedReason ?? 'You have unsaved changes'}</span>
            </p>
          </div>
          {saveButton(false)}
        </div>
      )}
    </div>
  );
}
