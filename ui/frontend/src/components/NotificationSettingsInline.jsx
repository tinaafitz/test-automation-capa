import React, { useState, useEffect } from 'react';
import { buildApiUrl } from '../config/api';

const NotificationSettingsInline = () => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [activeTab, setActiveTab] = useState('email');
  const [saveMessage, setSaveMessage] = useState(null); // {type: 'success' | 'error', text: string}

  const [settings, setSettings] = useState({
    slack_enabled: false,
    slack_webhook_url: '',
    email_enabled: false,
    smtp_server: '',
    smtp_port: 587,
    smtp_username: '',
    smtp_password: '',
    from_email: '',
    to_emails: [],
    use_tls: true,
    app_url: 'http://localhost:3000',
    notify_on_start: false,
    notify_on_complete: true,
    notify_on_failure: true,
    // Provision notification preferences
    notify_provision_start: false,
    notify_provision_success: true,
    notify_provision_failure: true,
    // Delete notification preferences
    notify_delete_start: false,
    notify_delete_success: true,
    notify_delete_failure: true,
  });

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const response = await fetch(buildApiUrl('/api/notification-settings'));
      if (response.ok) {
        const data = await response.json();
        if (data.settings) {
          setSettings(data.settings);
        }
      }
    } catch (error) {
      console.error('Failed to fetch notification settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveMessage(null);
    try {
      const response = await fetch(buildApiUrl('/api/notification-settings'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });

      if (response.ok) {
        setSaveMessage({ type: 'success', text: 'Notification settings saved successfully!' });
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        const error = await response.json();
        setSaveMessage({ type: 'error', text: `Failed to save settings: ${error.detail || 'Unknown error'}` });
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } catch (error) {
      setSaveMessage({ type: 'error', text: `Failed to save settings: ${error.message}` });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setSaving(false);
    }
  };

  const handleInputChange = (field, value) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
  };

  const handleEmailsChange = (emailsString) => {
    const emails = emailsString.split(',').map((e) => e.trim()).filter((e) => e);
    handleInputChange('to_emails', emails);
  };

  return (
    <div>
      {loading ? (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-cyan-600"></div>
          <p className="mt-4 text-gray-600">Loading settings...</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Success/Error Message Banner */}
          {saveMessage && (
            <div className={`px-4 py-3 rounded-lg border ${
              saveMessage.type === 'success'
                ? 'bg-green-50 border-green-200 text-green-800'
                : 'bg-red-50 border-red-200 text-red-800'
            }`}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{saveMessage.text}</span>
                <button
                  onClick={() => setSaveMessage(null)}
                  className="text-gray-500 hover:text-gray-700"
                >
                  ✕
                </button>
              </div>
            </div>
          )}

          {/* Tabs */}
          <div className="flex gap-2 border-b border-gray-200">
            <button
              onClick={() => setActiveTab('email')}
              className={`flex items-center gap-2 px-4 py-2 font-medium transition-colors border-b-2 ${
                activeTab === 'email'
                  ? 'border-cyan-600 text-cyan-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              📧 Email
            </button>
            <button
              onClick={() => setActiveTab('slack')}
              className={`flex items-center gap-2 px-4 py-2 font-medium transition-colors border-b-2 ${
                activeTab === 'slack'
                  ? 'border-cyan-600 text-cyan-600'
                  : 'border-transparent text-gray-600 hover:text-gray-900'
              }`}
            >
              💬 Slack
            </button>
          </div>

          {/* Email Tab */}
          {activeTab === 'email' && (
            <div className="space-y-4">
              {/* Enable Email */}
              <div className="flex items-center justify-between py-3">
                <div>
                  <h3 className="font-semibold text-gray-900">Enable Email Notifications</h3>
                  <p className="text-sm text-gray-600">Send notifications via email for provisioning jobs</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={settings.email_enabled}
                    onChange={(e) => handleInputChange('email_enabled', e.target.checked)}
                  />
                  <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-600"></div>
                </label>
              </div>

              {/* SMTP Server */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">SMTP Server *</label>
                <input
                  type="text"
                  value={settings.smtp_server}
                  onChange={(e) => handleInputChange('smtp_server', e.target.value)}
                  placeholder="smtp.gmail.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Common: smtp.gmail.com (Gmail), smtp-mail.outlook.com (Outlook), smtp.sendgrid.net (SendGrid)
                </p>
              </div>

              {/* SMTP Port and TLS */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">SMTP Port</label>
                  <input
                    type="number"
                    value={settings.smtp_port}
                    onChange={(e) => handleInputChange('smtp_port', parseInt(e.target.value))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500"
                  />
                  <p className="mt-1 text-xs text-gray-500">Common: 587 (TLS), 465 (SSL)</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Use TLS</label>
                  <label className="relative inline-flex items-center cursor-pointer mt-2">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={settings.use_tls}
                      onChange={(e) => handleInputChange('use_tls', e.target.checked)}
                    />
                    <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-600"></div>
                  </label>
                </div>
              </div>

              {/* SMTP Username */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">SMTP Username (optional)</label>
                <input
                  type="text"
                  value={settings.smtp_username}
                  onChange={(e) => handleInputChange('smtp_username', e.target.value)}
                  placeholder="user@example.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500"
                />
              </div>

              {/* SMTP Password */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">SMTP Password (optional)</label>
                <input
                  type="password"
                  value={settings.smtp_password}
                  onChange={(e) => handleInputChange('smtp_password', e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500"
                />
                <p className="mt-1 text-xs text-gray-500">For Gmail, use an App Password instead of your regular password</p>
              </div>

              {/* From Email */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">From Email Address *</label>
                <input
                  type="email"
                  value={settings.from_email}
                  onChange={(e) => handleInputChange('from_email', e.target.value)}
                  placeholder="notifications@example.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500"
                />
              </div>

              {/* To Emails */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Recipient Email Addresses *</label>
                <input
                  type="text"
                  value={settings.to_emails.join(', ')}
                  onChange={(e) => handleEmailsChange(e.target.value)}
                  placeholder="email1@example.com, email2@example.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500"
                />
                <p className="mt-1 text-xs text-gray-500">Separate multiple emails with commas</p>
              </div>
            </div>
          )}

          {/* Slack Tab */}
          {activeTab === 'slack' && (
            <div className="space-y-4">
              {/* Enable Slack */}
              <div className="flex items-center justify-between py-3">
                <div>
                  <h3 className="font-semibold text-gray-900">Enable Slack Notifications</h3>
                  <p className="text-sm text-gray-600">Send notifications to Slack for provisioning jobs</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    className="sr-only peer"
                    checked={settings.slack_enabled}
                    onChange={(e) => handleInputChange('slack_enabled', e.target.checked)}
                  />
                  <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-cyan-600"></div>
                </label>
              </div>

              {/* Slack Webhook URL */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Slack Webhook URL *</label>
                <input
                  type="text"
                  value={settings.slack_webhook_url}
                  onChange={(e) => handleInputChange('slack_webhook_url', e.target.value)}
                  placeholder="https://hooks.slack.com/services/..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500 font-mono text-sm"
                />
                <p className="mt-1 text-xs text-gray-500">Create a webhook in your Slack workspace settings</p>
              </div>
            </div>
          )}

          {/* Notification Preferences Section */}
          <div className="border-t pt-6 mt-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Notification Preferences</h3>
            <p className="text-sm text-gray-600 mb-4">
              Choose when you want to receive notifications for cluster operations
            </p>

            <div className="space-y-4">
              {/* Provisioning Notifications */}
              <details className="bg-gray-50 rounded-lg border border-gray-200">
                <summary className="cursor-pointer p-4 font-semibold text-gray-800 hover:bg-gray-100 rounded-lg">
                  Cluster Provisioning
                </summary>
                <div className="space-y-2 p-4 pt-2">
                  <label className="flex items-center gap-3 p-2 hover:bg-gray-100 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.notify_provision_start}
                      onChange={(e) => handleInputChange('notify_provision_start', e.target.checked)}
                      className="h-4 w-4 text-cyan-600 focus:ring-cyan-500 border-gray-300 rounded"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700">Provisioning starts</span>
                      <p className="text-xs text-gray-500">Receive notification when cluster provisioning begins</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-2 hover:bg-gray-100 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.notify_provision_success}
                      onChange={(e) => handleInputChange('notify_provision_success', e.target.checked)}
                      className="h-4 w-4 text-cyan-600 focus:ring-cyan-500 border-gray-300 rounded"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700">Provisioning completes</span>
                      <p className="text-xs text-gray-500">Receive notification when cluster is provisioned successfully</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-2 hover:bg-gray-100 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.notify_provision_failure}
                      onChange={(e) => handleInputChange('notify_provision_failure', e.target.checked)}
                      className="h-4 w-4 text-cyan-600 focus:ring-cyan-500 border-gray-300 rounded"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700">Provisioning failures only</span>
                      <p className="text-xs text-gray-500">Receive notification when cluster provisioning fails</p>
                    </div>
                  </label>
                </div>
              </details>

              {/* Deletion Notifications */}
              <details className="bg-gray-50 rounded-lg border border-gray-200">
                <summary className="cursor-pointer p-4 font-semibold text-gray-800 hover:bg-gray-100 rounded-lg">
                  Cluster Deletion
                </summary>
                <div className="space-y-2 p-4 pt-2">
                  <label className="flex items-center gap-3 p-2 hover:bg-gray-100 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.notify_delete_start}
                      onChange={(e) => handleInputChange('notify_delete_start', e.target.checked)}
                      className="h-4 w-4 text-cyan-600 focus:ring-cyan-500 border-gray-300 rounded"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700">Deletion starts</span>
                      <p className="text-xs text-gray-500">Receive notification when cluster deletion begins</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-2 hover:bg-gray-100 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.notify_delete_success}
                      onChange={(e) => handleInputChange('notify_delete_success', e.target.checked)}
                      className="h-4 w-4 text-cyan-600 focus:ring-cyan-500 border-gray-300 rounded"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700">Deletion completes</span>
                      <p className="text-xs text-gray-500">Receive notification when cluster is deleted successfully</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-2 hover:bg-gray-100 rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.notify_delete_failure}
                      onChange={(e) => handleInputChange('notify_delete_failure', e.target.checked)}
                      className="h-4 w-4 text-cyan-600 focus:ring-cyan-500 border-gray-300 rounded"
                    />
                    <div>
                      <span className="text-sm font-medium text-gray-700">Deletion failures only</span>
                      <p className="text-xs text-gray-500">Receive notification when cluster deletion fails</p>
                    </div>
                  </label>
                </div>
              </details>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-end pt-4 border-t">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-6 py-3 text-white rounded-lg transition-colors font-medium"
              style={!saving ? { backgroundColor: '#2684FF' } : { backgroundColor: '#9CA3AF' }}
              onMouseEnter={(e) => !saving && (e.currentTarget.style.backgroundColor = '#0065FF')}
              onMouseLeave={(e) => !saving && (e.currentTarget.style.backgroundColor = '#2684FF')}
            >
              {saving ? 'Saving...' : '💾 Save Settings'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationSettingsInline;
