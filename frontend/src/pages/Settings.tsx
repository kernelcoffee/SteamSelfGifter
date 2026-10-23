import { useState } from 'react';
import { Save, TestTube, AlertCircle, Eye, EyeOff, HelpCircle, ExternalLink } from 'lucide-react';
import { Card, Button, Input, Toggle, Loading } from '@/components/common';
import { useSettings, useUpdateSettings, useTestSession } from '@/hooks';
import { showSuccess, showError } from '@/stores/uiStore';
import type { Settings as SettingsType } from '@/types';

// Bounds mirror the backend schema (ge=5, le=10080: five minutes to one week)
const ENDING_SOON_THRESHOLD_MIN = 5;
const ENDING_SOON_THRESHOLD_MAX = 10080;
const ENDING_SOON_THRESHOLD_DEFAULT = 60;

/** Parse the threshold field's text; null unless it is an integer in range. */
function parseThreshold(text: string): number | null {
  if (!/^\d+$/.test(text.trim())) return null;
  const value = Number(text.trim());
  return value >= ENDING_SOON_THRESHOLD_MIN && value <= ENDING_SOON_THRESHOLD_MAX ? value : null;
}

/**
 * Settings page
 * Configure credentials, DLC settings, and auto-join rules
 */
export function Settings() {
  const { data: settings, isLoading, error } = useSettings();

  if (isLoading) {
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
          <div className="flex items-center gap-3 text-red-500">
            <AlertCircle size={24} />
            <span>Failed to load settings. Is the backend running?</span>
          </div>
        </Card>
      </div>
    );
  }

  // Remount the form whenever the server state changes (e.g. after a save's
  // refetch) so it re-initializes from fresh data without effect-driven state.
  return <SettingsForm key={settings.updated_at} settings={settings} />;
}

function SettingsForm({ settings }: { settings: SettingsType }) {
  const updateSettings = useUpdateSettings();
  const testSession = useTestSession();

  const [formData, setFormData] = useState<Partial<SettingsType>>(() => ({
    phpsessid: settings.phpsessid ?? '',
    user_agent: settings.user_agent,
    dlc_priority_enabled: settings.dlc_priority_enabled,
    safety_check_enabled: settings.safety_check_enabled,
    auto_hide_unsafe: settings.auto_hide_unsafe,
    autojoin_enabled: settings.autojoin_enabled,
    autojoin_start_at: settings.autojoin_start_at,
    autojoin_stop_at: settings.autojoin_stop_at,
    autojoin_min_price: settings.autojoin_min_price,
    autojoin_min_score: settings.autojoin_min_score,
    autojoin_min_reviews: settings.autojoin_min_reviews,
    autojoin_max_game_age: settings.autojoin_max_game_age,
    wishlist_priority_enabled: settings.wishlist_priority_enabled,
    ending_soon_priority_enabled: settings.ending_soon_priority_enabled,
    ending_soon_threshold_minutes: settings.ending_soon_threshold_minutes,
    scan_interval_minutes: settings.scan_interval_minutes,
    max_entries_per_cycle: settings.max_entries_per_cycle,
    automation_enabled: settings.automation_enabled,
    max_scan_pages: settings.max_scan_pages,
    entry_delay_min: settings.entry_delay_min,
    entry_delay_max: settings.entry_delay_max,
    log_retention_days: settings.log_retention_days,
  }));
  const [hasChanges, setHasChanges] = useState(false);
  const [showPhpsessid, setShowPhpsessid] = useState(false);

  const savedThreshold = settings.ending_soon_threshold_minutes ?? ENDING_SOON_THRESHOLD_DEFAULT;
  // Raw text of the threshold field: lets the user clear it and type freely.
  // formData only receives the number once the text is a valid threshold.
  const [thresholdText, setThresholdText] = useState(() => String(savedThreshold));
  const parsedThreshold = parseThreshold(thresholdText);
  const thresholdError =
    formData.ending_soon_priority_enabled && parsedThreshold === null
      ? `Must be between ${ENDING_SOON_THRESHOLD_MIN} and ${ENDING_SOON_THRESHOLD_MAX} minutes`
      : undefined;
  const isValid = !thresholdError;
  // Shown next to the disabled Save buttons, which may be far from the inline error.
  const saveBlockedReason = isValid
    ? undefined
    : `Fix the ending soon threshold (${ENDING_SOON_THRESHOLD_MIN} to ${ENDING_SOON_THRESHOLD_MAX} minutes) to save`;

  const handleChange = (field: keyof SettingsType, value: string | number | boolean | null) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const handleThresholdChange = (raw: string) => {
    setThresholdText(raw);
    const parsed = parseThreshold(raw);
    if (parsed !== null) {
      setFormData(prev => ({ ...prev, ending_soon_threshold_minutes: parsed }));
    }
    setHasChanges(true);
  };

  // Turning the lift off hides the threshold input, so any draft threshold
  // (valid or not) is discarded and the saved value restored: nothing hidden
  // from the user is ever sent.
  const handleEndingSoonToggle = (checked: boolean) => {
    setFormData(prev => ({
      ...prev,
      ending_soon_priority_enabled: checked,
      ...(checked ? {} : { ending_soon_threshold_minutes: savedThreshold }),
    }));
    if (!checked) {
      setThresholdText(String(savedThreshold));
    }
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!isValid) return;
    try {
      await updateSettings.mutateAsync(formData);
      showSuccess('Settings saved successfully');
      setHasChanges(false);
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <Button
          onClick={handleSave}
          isLoading={updateSettings.isPending}
          disabled={!hasChanges || !isValid}
          title={saveBlockedReason}
          icon={Save}
        >
          Save Changes
        </Button>
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
              value={formData.phpsessid ?? ''}
              onChange={(e) => handleChange('phpsessid', e.target.value)}
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
            value={formData.user_agent ?? ''}
            onChange={(e) => handleChange('user_agent', e.target.value)}
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
      <Card title="Automation Settings">
        <div className="space-y-4">
          <Toggle
            label="Enable Automation"
            description="Allow the scheduler to run automatic scans and entries"
            checked={formData.automation_enabled ?? false}
            onChange={(checked) => handleChange('automation_enabled', checked)}
          />
          <Toggle
            label="Enable Auto-Join"
            description="Automatically enter eligible giveaways"
            checked={formData.autojoin_enabled ?? false}
            onChange={(checked) => handleChange('autojoin_enabled', checked)}
          />
        </div>
      </Card>

      {/* Safety Settings */}
      <Card title="Safety Settings">
        <div className="space-y-4">
          <Toggle
            label="Enable Trap Detection"
            description="Scan each giveaway's description and comments for trap language (e.g., 'do not enter', 'bot trap', 'you will be banned') before auto-entering"
            checked={formData.safety_check_enabled ?? true}
            onChange={(checked) => handleChange('safety_check_enabled', checked)}
          />
          <Toggle
            label="Auto-Hide Unsafe Giveaways"
            description="Automatically hide detected trap giveaways on SteamGifts"
            checked={formData.auto_hide_unsafe ?? true}
            onChange={(checked) => handleChange('auto_hide_unsafe', checked)}
          />
        </div>
        <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
          Unchecked giveaways are scored by a background sweep each cycle. Outright traps are
          hidden; borderline scores (50&ndash;84) are skipped by auto-entry but stay visible with a
          Borderline badge so you can review them and re-check manually.
        </p>
      </Card>

      {/* Auto-Join Rules */}
      <Card title="Auto-Join Rules">
        <div className="mb-4">
          <Toggle
            label="Prioritize Wishlist"
            description="Wishlist giveaways skip the filters below and are entered before everything else (the points budget still applies)"
            checked={formData.wishlist_priority_enabled ?? true}
            onChange={(checked) => handleChange('wishlist_priority_enabled', checked)}
          />
        </div>
        <div className="mb-4">
          <Toggle
            label="Prioritize DLC"
            description="DLC giveaways skip the filters below and are entered after wishlist ones — the DLC listing only shows content for games you own"
            checked={formData.dlc_priority_enabled ?? false}
            onChange={(checked) => handleChange('dlc_priority_enabled', checked)}
          />
        </div>
        <div className="mb-4">
          <Toggle
            label="Enter giveaways ending soon first"
            description="Giveaways that pass the filters below and end within the threshold are entered after wishlist and DLC ones but before the rest, soonest first"
            checked={formData.ending_soon_priority_enabled ?? false}
            onChange={handleEndingSoonToggle}
          />
          {formData.ending_soon_priority_enabled && (
            <div className="mt-3 max-w-xs">
              <Input
                label="Ending Soon Threshold (minutes)"
                type="number"
                min={ENDING_SOON_THRESHOLD_MIN}
                max={ENDING_SOON_THRESHOLD_MAX}
                value={thresholdText}
                onChange={(e) => handleThresholdChange(e.target.value)}
                helperText={`A giveaway counts as ending soon when it ends within this many minutes (${ENDING_SOON_THRESHOLD_MIN} to ${ENDING_SOON_THRESHOLD_MAX})`}
                error={thresholdError}
              />
            </div>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Start at Points"
            type="number"
            value={formData.autojoin_start_at ?? 350}
            onChange={(e) => handleChange('autojoin_start_at', parseInt(e.target.value) || 0)}
            helperText="Only auto-join when you have at least this many points"
          />
          <Input
            label="Stop at Points"
            type="number"
            value={formData.autojoin_stop_at ?? 200}
            onChange={(e) => handleChange('autojoin_stop_at', parseInt(e.target.value) || 0)}
            helperText="Stop auto-joining when points drop below this"
          />
          <Input
            label="Min Game Price ($)"
            type="number"
            value={formData.autojoin_min_price ?? 10}
            onChange={(e) => handleChange('autojoin_min_price', parseInt(e.target.value) || 0)}
            helperText="Only enter games worth at least this much"
          />
          <Input
            label="Min Review Score"
            type="number"
            value={formData.autojoin_min_score ?? 7}
            onChange={(e) => handleChange('autojoin_min_score', parseInt(e.target.value) || 0)}
            helperText="Minimum Steam review score (0-10)"
          />
          <Input
            label="Min Review Count"
            type="number"
            value={formData.autojoin_min_reviews ?? 1000}
            onChange={(e) => handleChange('autojoin_min_reviews', parseInt(e.target.value) || 0)}
            helperText="Minimum number of Steam reviews"
          />
          <Input
            label="Max Game Age (years)"
            type="number"
            value={formData.autojoin_max_game_age ?? ''}
            onChange={(e) => handleChange('autojoin_max_game_age', e.target.value ? parseInt(e.target.value) : null)}
            helperText="Only enter games released within this many years (empty = no limit)"
          />
        </div>
      </Card>

      {/* Scheduler Settings */}
      <Card title="Scheduler Settings">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Scan Interval (minutes)"
            type="number"
            value={formData.scan_interval_minutes ?? 30}
            onChange={(e) => handleChange('scan_interval_minutes', parseInt(e.target.value) || 30)}
            helperText="How often to scan for new giveaways"
          />
          <Input
            label="Max Scan Pages"
            type="number"
            value={formData.max_scan_pages ?? 3}
            onChange={(e) => handleChange('max_scan_pages', parseInt(e.target.value) || 3)}
            helperText="Maximum pages to scan per cycle"
          />
          <Input
            label="Max Entries per Cycle"
            type="number"
            value={formData.max_entries_per_cycle ?? ''}
            onChange={(e) => handleChange('max_entries_per_cycle', e.target.value ? parseInt(e.target.value) : null)}
            helperText="Limit entries per cycle (empty = unlimited)"
          />
          <Input
            label="Log Retention (days)"
            type="number"
            value={formData.log_retention_days ?? 30}
            onChange={(e) => handleChange('log_retention_days', parseInt(e.target.value) || 0)}
            helperText="Activity logs older than this are pruned (0 = keep forever)"
          />
        </div>
      </Card>

      {/* Rate Limiting */}
      <Card title="Rate Limiting">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Min Entry Delay (seconds)"
            type="number"
            value={formData.entry_delay_min ?? 8}
            onChange={(e) => handleChange('entry_delay_min', parseInt(e.target.value) || 8)}
            helperText="Minimum delay between entries"
          />
          <Input
            label="Max Entry Delay (seconds)"
            type="number"
            value={formData.entry_delay_max ?? 12}
            onChange={(e) => handleChange('entry_delay_max', parseInt(e.target.value) || 12)}
            helperText="Maximum delay between entries"
          />
        </div>
        <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
          Random delays between these values help avoid rate limiting and detection.
        </p>
      </Card>

      {/* Save Button (Bottom) */}
      {hasChanges && (
        <div className="flex items-center justify-between p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
          <div className="flex items-center gap-2 text-yellow-700 dark:text-yellow-400">
            <AlertCircle size={20} />
            <span>{saveBlockedReason ?? 'You have unsaved changes'}</span>
          </div>
          <Button
            onClick={handleSave}
            isLoading={updateSettings.isPending}
            disabled={!isValid}
            title={saveBlockedReason}
            icon={Save}
          >
            Save Changes
          </Button>
        </div>
      )}
    </div>
  );
}
