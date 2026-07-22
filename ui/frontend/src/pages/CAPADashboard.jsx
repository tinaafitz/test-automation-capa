/* eslint-disable no-unused-vars */
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircleIcon, Cog6ToothIcon, ClockIcon, TrashIcon, XCircleIcon, ArrowPathIcon } from '@heroicons/react/24/outline';

import CapaSidebar from '../components/sidebar/CapaSidebar';
import RosaHcpClustersSection from '../components/sections/RosaHcpClustersSection';
import CredentialsModal from '../components/modals/CredentialsModal';
import MCEEnvironmentSelector from '../components/MCEEnvironmentSelector';
import ActiveEnvironmentBanner from '../components/ActiveEnvironmentBanner';
import { YamlEditorModal } from '../components/YamlEditorModal';
import { RosaProvisionModal } from '../components/RosaProvisionModal';
import ResourcesViewer from '../components/ResourcesViewer';
import NotificationSettingsInline from '../components/NotificationSettingsInline';
import WorkflowBuilder from '../components/WorkflowBuilder';
import ClusterActions from '../components/ClusterActions';
import WorkflowOrchestratorView from '../components/WorkflowOrchestratorView';
import {
  useApiStatusContext,
  useRecentOperationsContext,
  useApp,
  useAppDispatch,
} from '../store/AppContext';
import { AppActionTypes } from '../store/AppContext';
import {
  buildApiUrl,
  API_ENDPOINTS,
  validateApiResponse,
  extractSafeErrorMessage,
} from '../config/api';

/**
 * TerminalInline - Inline terminal component (not a modal)
 */
const TerminalInline = () => {
  const [command, setCommand] = useState('');
  const [output, setOutput] = useState(
    'Welcome to MCE Terminal! Type commands or select from templates.\n'
  );
  const [history, setHistory] = useState([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [executing, setExecuting] = useState(false);
  const outputRef = useRef(null);

  // Scroll to bottom when output changes
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [output]);

  // Command execution
  const executeCommand = async () => {
    if (!command.trim() || executing) return;

    setExecuting(true);
    const timestamp = new Date().toLocaleTimeString();

    setOutput((prev) => `${prev}\n$ ${command}\n`);

    const newHistoryItem = {
      command: command.trim(),
      timestamp: new Date().toISOString(),
      timestampFormatted: timestamp,
    };
    setHistory((prev) => [newHistoryItem, ...prev].slice(0, 100));
    setHistoryIndex(-1);

    try {
      const response = await fetch(buildApiUrl('/api/ocp/execute-command'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: command.trim() }),
      });

      const data = await response.json();

      if (data.success) {
        setOutput((prev) => `${prev}${data.output}\n`);
      } else {
        setOutput(
          (prev) => `${prev}Error: ${data.error || 'Command failed'}\n${data.output || ''}\n`
        );
      }
    } catch (err) {
      setOutput((prev) => `${prev}Error: Failed to execute command - ${err.message}\n`);
    } finally {
      setExecuting(false);
      setCommand('');
    }
  };

  // Keyboard handler for history navigation
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      executeCommand();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (history.length > 0) {
        const newIndex = Math.min(historyIndex + 1, history.length - 1);
        setHistoryIndex(newIndex);
        setCommand(history[newIndex].command);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex > 0) {
        const newIndex = historyIndex - 1;
        setHistoryIndex(newIndex);
        setCommand(history[newIndex].command);
      } else if (historyIndex === 0) {
        setHistoryIndex(-1);
        setCommand('');
      }
    }
  };


  return (
    <div>
      <p className="text-gray-600 mb-4">Execute commands directly on your MCE environment.</p>

      {/* Terminal - Full width */}
      <div className="flex flex-col">
          {/* Terminal Output */}
          <div
            ref={outputRef}
            className="bg-black text-green-400 font-mono text-sm p-4 rounded-lg h-96 overflow-y-auto mb-4"
            style={{ fontFamily: 'Monaco, Courier, monospace' }}
          >
            <pre className="whitespace-pre-wrap">{output}</pre>
          </div>

          {/* Command Input */}
          <div className="flex items-center space-x-3">
            <div className="flex-1 relative">
              <span className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-500 font-mono">
                $
              </span>
              <input
                type="text"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Enter command... (↑/↓ for history)"
                disabled={executing}
                className="w-full pl-8 pr-4 py-3 border rounded focus:ring-2 focus:border-transparent font-mono text-sm disabled:bg-gray-100"
                style={{ borderColor: '#2684FF' }}
              />
            </div>
            <button
              onClick={executeCommand}
              disabled={executing || !command.trim()}
              className={`px-5 py-2.5 text-sm font-semibold text-white rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                !executing && command.trim()
                  ? 'bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 shadow-sm hover:shadow-md'
                  : 'bg-gray-400'
              }`}
            >
              {executing ? 'Running...' : 'Execute'}
            </button>
            <button
              onClick={() => {
                setOutput('Terminal cleared.\n');
                setCommand('');
              }}
              className="px-4 py-3 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition-colors"
              title="Clear Terminal"
            >
              🗑️ Clear
            </button>
          </div>

        {/* Command History */}
        {history.length > 0 && (
          <div className="mt-4">
            <details className="bg-gray-50 rounded-lg p-4">
              <summary className="cursor-pointer font-medium text-sm text-gray-700">
                Command History ({history.length})
              </summary>
              <div className="mt-3 space-y-2 max-h-40 overflow-y-auto">
                {history.slice(0, 10).map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2 bg-white rounded border cursor-pointer hover:bg-gray-50"
                    onClick={() => setCommand(item.command)}
                  >
                    <span className="font-mono text-xs text-gray-800 truncate">
                      {item.command}
                    </span>
                    <span className="text-xs text-gray-500 ml-2 flex-shrink-0">
                      {item.timestampFormatted}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * CAPADashboardContent - Inner component with all the dashboard logic
 */
const CAPADashboardContent = () => {
  const navigate = useNavigate();
  const app = useApp();
  const dispatch = useAppDispatch();
  const apiStatus = useApiStatusContext();
  const recentOps = useRecentOperationsContext();

  // UI State
  const [activeSection, setActiveSection] = useState('credentials');
  const [showEnvironments, setShowEnvironments] = useState(false);
  const [showYamlEditorModal, setShowYamlEditorModal] = useState(false);
  const [yamlEditorData, setYamlEditorData] = useState(null);
  const [provisionViewMode, setProvisionViewMode] = useState('form'); // 'form' or 'yaml'
  const [credentialsRefreshKey, setCredentialsRefreshKey] = useState(0);
  const [verificationResults, setVerificationResults] = useState(null);
  const [configurationResults, setConfigurationResults] = useState(null);
  const [provisionResults, setProvisionResults] = useState(null);
  const [selectedTestSuite, setSelectedTestSuite] = useState(null); // For test suite provisioning
  const [mceLastConfigured, setMceLastConfigured] = useState(null);
  const [isConfiguring, setIsConfiguring] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [toastType, setToastType] = useState('');
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [provisionJobId, setProvisionJobId] = useState(null);
  const [provisionOpId, setProvisionOpId] = useState(null);
  const [isCheckingProvisionJob, setIsCheckingProvisionJob] = useState(false);

  const {
    ocpStatus,
    mceFeatures,
    mceInfo,
    mceLastVerified,
    loading: apiLoading,
    refreshAllStatus,
    setOcpStatus,
    setMceLastVerified,
  } = apiStatus;

  const { addToRecent, updateRecentOperationStatus } = recentOps;

  // Check for running provision jobs when navigating to provision section
  useEffect(() => {
    if (activeSection === 'provision') {
      checkForRunningProvisionJob();
    }
  }, [activeSection]);

  // Check for running configure jobs when navigating to configure section
  useEffect(() => {
    if (activeSection === 'configure') {
      checkForRunningConfigureJob();
    }
  }, [activeSection]);

  // Check for running verify jobs when navigating to verify section
  useEffect(() => {
    if (activeSection === 'verify') {
      checkForRunningVerifyJob();
    }
  }, [activeSection]);

  // Function to check for running provision jobs and restore their output
  const checkForRunningProvisionJob = async () => {
    setIsCheckingProvisionJob(true);
    try {
      const response = await fetch(buildApiUrl('/api/jobs'));
      const data = await response.json();

      if (data.success && data.jobs) {
        // Find the most recent running provision job
        const runningProvisionJob = data.jobs.find(
          (job) =>
            job.status === 'running' &&
            job.description &&
            job.description.includes('Provision ROSA HCP')
        );

        if (runningProvisionJob) {
          console.log('📦 Found running provision job:', runningProvisionJob.id);

          // Fetch current logs
          const logsResponse = await fetch(buildApiUrl(`/api/jobs/${runningProvisionJob.id}/logs`));
          const logsData = await logsResponse.json();
          const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';

          // Set provision results to show the running job
          setProvisionJobId(runningProvisionJob.id);
          setProvisionResults({
            success: true,
            timestamp: new Date().toISOString(),
            output: currentOutput || 'Provisioning in progress...',
          });
          setIsProvisioning(true);

          // Continue polling this job
          pollProvisionJob(runningProvisionJob.id);
        } else {
          // No running job, clear results and show form
          setProvisionResults(null);
          setProvisionViewMode('form');
        }
      }
    } catch (error) {
      console.error('Error checking for running provision jobs:', error);
      setProvisionResults(null);
      setProvisionViewMode('form');
    } finally {
      setIsCheckingProvisionJob(false);
    }
  };

  // Function to poll a provision job and update results
  const pollProvisionJob = async (jobId) => {
    const maxAttempts = 1800; // 30 minutes max
    let attempts = 0;
    setProvisionJobId(jobId);

    const poll = async () => {
      if (attempts >= maxAttempts) {
        console.log('⏱️ Max polling attempts reached');
        setIsProvisioning(false);
        setProvisionJobId(null);
        return;
      }

      attempts++;

      try {
        const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`));
        const jobData = await jobResponse.json();

        // Fetch logs and agent stats
        const [logsResponse, agentResponse] = await Promise.all([
          fetch(buildApiUrl(`/api/jobs/${jobId}/logs`)),
          fetch(buildApiUrl(`/api/jobs/${jobId}/agent-stats`)).catch(() => null),
        ]);
        const logsData = await logsResponse.json();
        const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';
        const agentData = agentResponse ? await agentResponse.json().catch(() => null) : null;
        const agentStats = agentData?.agent_stats || null;

        // Update provision results every poll with current output
        if (currentOutput) {
          setProvisionResults({
            success: jobData.status !== 'failed',
            timestamp: new Date().toISOString(),
            output: currentOutput,
            isRunning: jobData.status === 'running',
            agentStats,
          });
        }

        if (jobData.status === 'completed') {
          console.log('✅ Provision job completed');
          setProvisionResults({
            success: true,
            timestamp: new Date().toISOString(),
            output: currentOutput || 'Provisioning completed successfully',
            isRunning: false,
            agentStats,
          });
          setIsProvisioning(false);
          setProvisionJobId(null);
          return;
        } else if (jobData.status === 'failed') {
          console.log('❌ Provision job failed');
          setProvisionResults({
            success: false,
            timestamp: new Date().toISOString(),
            output: currentOutput || 'Provisioning failed',
            isRunning: false,
            agentStats,
          });
          setIsProvisioning(false);
          setProvisionJobId(null);
          return;
        }

        // Continue polling if still running
        if (jobData.status === 'running') {
          setTimeout(poll, 2000); // Poll every 2 seconds
        }
      } catch (error) {
        console.error('Error polling provision job:', error);
        setIsProvisioning(false);
        setProvisionJobId(null);
      }
    };

    poll();
  };

  // Function to check for running configure jobs and restore their output
  const checkForRunningConfigureJob = async () => {
    setIsConfiguring(true);
    try {
      const response = await fetch(buildApiUrl('/api/jobs'));
      const data = await response.json();

      if (data.success && data.jobs) {
        // Find the most recent running configure job
        const runningConfigureJob = data.jobs.find(
          (job) =>
            job.status === 'running' &&
            job.description &&
            job.description.includes('Configure MCE CAPI/CAPA')
        );

        if (runningConfigureJob) {
          console.log('⚙️ Found running configure job:', runningConfigureJob.id);

          // Fetch current logs
          const logsResponse = await fetch(buildApiUrl(`/api/jobs/${runningConfigureJob.id}/logs`));
          const logsData = await logsResponse.json();
          const currentOutput = logsData.logs ? logsData.logs.join('\\n') : '';

          // Set configuration results to show the running job
          setConfigurationResults({
            success: true,
            timestamp: new Date().toISOString(),
            output: currentOutput || 'Configuration in progress...',
          });

          // Continue polling this job
          pollConfigureJob(runningConfigureJob.id);
        } else {
          // No running job, clear results
          setConfigurationResults(null);
          setIsConfiguring(false);
        }
      }
    } catch (error) {
      console.error('Error checking for running configure jobs:', error);
      setConfigurationResults(null);
      setIsConfiguring(false);
    }
  };

  // Function to poll a configure job and update results
  const pollConfigureJob = async (jobId) => {
    const maxAttempts = 900; // 15 minutes max
    let attempts = 0;

    const poll = async () => {
      if (attempts >= maxAttempts) {
        console.log('⏱️ Max polling attempts reached for configure job');
        setIsConfiguring(false);
        return;
      }

      attempts++;

      try {
        const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`));
        const jobData = await jobResponse.json();

        // Fetch logs
        const logsResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}/logs`));
        const logsData = await logsResponse.json();
        const currentOutput = logsData.logs ? logsData.logs.join('\\n') : '';

        // Update configuration results every 5 seconds with current output
        if (attempts % 5 === 0 && currentOutput) {
          setConfigurationResults({
            success: jobData.status !== 'failed',
            timestamp: new Date().toISOString(),
            output: currentOutput,
          });
        }

        if (jobData.status === 'completed') {
          console.log('✅ Configure job completed');
          setConfigurationResults({
            success: true,
            timestamp: new Date().toISOString(),
            output: currentOutput || 'Configuration completed successfully',
          });
          setIsConfiguring(false);
          setMceLastConfigured(new Date().toISOString());
          await refreshAllStatus();
          return;
        } else if (jobData.status === 'failed') {
          console.log('❌ Configure job failed');
          setConfigurationResults({
            success: false,
            timestamp: new Date().toISOString(),
            output: currentOutput || 'Configuration failed',
          });
          setIsConfiguring(false);
          return;
        }

        // Continue polling if still running
        if (jobData.status === 'running') {
          setTimeout(poll, 1000); // Poll every 1 second
        }
      } catch (error) {
        console.error('Error polling configure job:', error);
        setIsConfiguring(false);
      }
    };

    poll();
  };

  // Function to check for running verify jobs and restore their output
  const checkForRunningVerifyJob = async () => {
    setIsVerifying(true);
    try {
      const response = await fetch(buildApiUrl('/api/jobs'));
      const data = await response.json();

      if (data.success && data.jobs) {
        // Find the most recent running verify job
        const runningVerifyJob = data.jobs.find(
          (job) =>
            job.status === 'running' &&
            job.description &&
            job.description.includes('MCE Environment Verification')
        );

        if (runningVerifyJob) {
          console.log('🔍 Found running verify job:', runningVerifyJob.id);

          // Fetch current logs
          const logsResponse = await fetch(buildApiUrl(`/api/jobs/${runningVerifyJob.id}/logs`));
          const logsData = await logsResponse.json();
          const currentOutput = logsData.logs ? logsData.logs.join('\\n') : '';

          // Set verification results to show the running job
          setVerificationResults({
            success: true,
            timestamp: new Date().toISOString(),
            output: currentOutput || 'Verification in progress...',
          });

          // Continue polling this job
          pollVerifyJob(runningVerifyJob.id);
        } else {
          // No running job, clear results
          setVerificationResults(null);
          setIsVerifying(false);
        }
      }
    } catch (error) {
      console.error('Error checking for running verify jobs:', error);
      setVerificationResults(null);
      setIsVerifying(false);
    }
  };

  // Function to poll a verify job and update results
  const pollVerifyJob = async (jobId) => {
    const maxAttempts = 60; // 60 seconds max for verification
    let attempts = 0;

    const poll = async () => {
      if (attempts >= maxAttempts) {
        console.log('⏱️ Max polling attempts reached for verify job');
        setIsVerifying(false);
        return;
      }

      attempts++;

      try {
        const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`));
        const jobData = await jobResponse.json();

        // Fetch logs
        const logsResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}/logs`));
        const logsData = await logsResponse.json();
        const currentOutput = logsData.logs ? logsData.logs.join('\\n') : '';

        // Update verification results every 3 seconds with current output
        if (attempts % 3 === 0 && currentOutput) {
          setVerificationResults({
            success: jobData.status !== 'failed',
            timestamp: new Date().toISOString(),
            output: currentOutput,
          });
        }

        if (jobData.status === 'completed') {
          console.log('✅ Verify job completed');
          setVerificationResults({
            success: true,
            timestamp: new Date().toISOString(),
            output: currentOutput || 'Verification completed successfully',
          });
          setIsVerifying(false);
          setMceLastVerified(new Date().toISOString());
          await refreshAllStatus();
          setCredentialsRefreshKey(prev => prev + 1);
          return;
        } else if (jobData.status === 'failed') {
          console.log('❌ Verify job failed');
          const output = currentOutput || 'Verification failed';

          // Check if error indicates environment needs configuration (not a real failure)
          const needsConfiguration =
            output.includes('Environment not configured yet') ||
            output.includes('CAPI controller not found') ||
            output.includes('CAPA controller not found') ||
            output.includes('Ready to set up');

          if (needsConfiguration) {
            setVerificationResults({
              success: null,
              needsConfiguration: true,
              timestamp: new Date().toISOString(),
              output,
            });
          } else {
            setVerificationResults({
              success: false,
              timestamp: new Date().toISOString(),
              output,
            });
          }
          setIsVerifying(false);
          return;
        }

        // Continue polling if still running
        if (jobData.status === 'running') {
          setTimeout(poll, 1000); // Poll every 1 second
        }
      } catch (error) {
        console.error('Error polling verify job:', error);
        setIsVerifying(false);
      }
    };

    poll();
  };

  // Copy handler for playbook output
  const [copySuccess, setCopySuccess] = useState('');

  const handleCopyOutput = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopySuccess('Copied!');
      setTimeout(() => setCopySuccess(''), 2000);
    }).catch(err => {
      console.error('Failed to copy text: ', err);
      setCopySuccess('Failed to copy');
      setTimeout(() => setCopySuccess(''), 2000);
    });
  };

  // ============================================================================
  // Handler Functions (from original MCEEnvironment.jsx)
  // ============================================================================

  // Handle MCE verification
  const handleMceVerification = async () => {
    const verifyId = `verify-mce-${Date.now()}`;

    // Clear previous results and set loading state
    setVerificationResults(null);
    setIsVerifying(true);

    try {
      addToRecent({
        id: verifyId,
        title: '🔍 MCE Environment Verification',
        color: 'bg-cyan-600',
        status: '🚀 Starting verification...',
        environment: 'mce',
        playbook: 'tasks/validate-capa-environment.yml',
        output: 'Initializing MCE environment verification...\nConnecting to OpenShift cluster...\nValidating MCE components...',
      });

      // Start the verification task
      const response = await fetch(buildApiUrl(API_ENDPOINTS.ANSIBLE_RUN_TASK), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_file: 'tasks/validate-capa-environment.yml',
          extra_vars: {},
        }),
      });

      const result = await response.json();
      console.log('📊 Verification API response:', result);

      if (!result.success || !result.job_id) {
        throw new Error(result.message || 'Failed to start verification');
      }

      const jobId = result.job_id;
      console.log(`🔍 Polling job status for job_id: ${jobId}`);

      // Poll for job completion
      const pollJobStatus = async () => {
        const maxAttempts = 60; // 60 attempts = 1 minute max wait (verification is usually quick)
        let attempts = 0;

        while (attempts < maxAttempts) {
          attempts++;
          console.log(`📡 Polling attempt ${attempts}/${maxAttempts}`);

          const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`));
          const jobData = await jobResponse.json();
          console.log(`📋 Job status:`, jobData);

          // Fetch logs regardless of status to show real-time output
          const logsResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}/logs`));
          const logsData = await logsResponse.json();
          const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';

          if (jobData.status === 'completed') {
            // Success - update with final logs
            const output = currentOutput || 'Verification completed successfully';

            updateRecentOperationStatus(verifyId, '✅ MCE environment verified successfully!', output);
            setMceLastVerified(new Date().toISOString());
            const successResults = {
              success: true,
              timestamp: new Date().toISOString(),
              output,
            };
            console.log('✅ Setting verification results (success):', successResults);
            setVerificationResults(successResults);
            setIsVerifying(false);
            await refreshAllStatus();
            // Force ActiveEnvironmentBanner to refresh and show verified status
            setCredentialsRefreshKey(prev => prev + 1);
            return;
          } else if (jobData.status === 'failed') {
            // Failure - but check if it's a configuration issue (not a real failure)
            const output = currentOutput || (jobData.error || jobData.message || 'Verification failed');

            // Check if error indicates environment needs configuration (not a real failure)
            const needsConfiguration =
              output.includes('Environment not configured yet') ||
              output.includes('CAPI controller not found') ||
              output.includes('CAPA controller not found') ||
              output.includes('Ready to set up');

            if (needsConfiguration) {
              // This is not a failure - environment just needs configuration
              updateRecentOperationStatus(verifyId, '🆕 Configuration Required', output);
              const configNeededResults = {
                success: null, // null indicates "needs config", not success or failure
                needsConfiguration: true,
                timestamp: new Date().toISOString(),
                output,
              };
              console.log('🆕 Setting verification results (needs configuration):', configNeededResults);
              setVerificationResults(configNeededResults);
            } else {
              // This is a real failure (credentials, network, etc.)
              // Extract error summary from the message
              let errorSummary = '❌ Verification failed';

              // Try to extract the specific error from jobData.message (backend already parsed it)
              if (jobData.message && jobData.message.includes(':')) {
                // Message format: "Verification failed: CREDENTIAL VERIFICATION FAILED"
                const parts = jobData.message.split(':');
                if (parts.length > 1) {
                  errorSummary = '❌ ' + parts.slice(1).join(':').trim();
                }
              } else if (output.includes('CREDENTIAL')) {
                errorSummary = '❌ Credential issue';
              } else if (output.includes('LOGIN FAILED') || output.includes('authentication')) {
                errorSummary = '❌ Authentication failed';
              } else if (output.includes('network') || output.includes('connection')) {
                errorSummary = '❌ Connection failed';
              }

              updateRecentOperationStatus(verifyId, errorSummary, output);
              const failureResults = {
                success: false,
                timestamp: new Date().toISOString(),
                output,
              };
              console.log('❌ Setting verification results (failure):', failureResults);
              setVerificationResults(failureResults);
            }
            setIsVerifying(false);
            return;
          }

          // Still running - update with current logs every 3 seconds
          if (attempts % 3 === 0 && currentOutput) {
            updateRecentOperationStatus(verifyId, '🔍 Verifying...', currentOutput);
            // Also update the inline display with real-time output
            setVerificationResults({
              success: true,
              timestamp: new Date().toISOString(),
              output: currentOutput,
            });
          }

          // Wait and poll again
          await new Promise((resolve) => setTimeout(resolve, 1000)); // Wait 1 second
        }

        // Timeout
        throw new Error('Verification timed out after 60 seconds');
      };

      await pollJobStatus();
    } catch (error) {
      console.error('Verification error:', error);
      updateRecentOperationStatus(verifyId, '❌ Verification error', extractSafeErrorMessage(error));
      setVerificationResults({
        success: false,
        timestamp: new Date().toISOString(),
        output: extractSafeErrorMessage(error),
      });
      setIsVerifying(false);
    }
  };

  // Handle configuration
  const handleConfigure = async () => {
    const configureId = `configure-mce-${Date.now()}`;

    // Clear previous results and set loading state
    setConfigurationResults(null);
    setIsConfiguring(true);

    try {
      addToRecent({
        id: configureId,
        title: '⚙️ Configure MCE CAPI/CAPA Environment',
        color: 'bg-cyan-600',
        status: '🚀 Starting configuration...',
        environment: 'mce',
        playbook: 'playbooks/configure_mce_environment.yml',
        output: 'Initializing MCE CAPI/CAPA configuration...\nEnabling cluster-api components...',
      });

      // Start the configuration task
      const response = await fetch(buildApiUrl(API_ENDPOINTS.ANSIBLE_RUN_PLAYBOOK), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          playbook: 'playbooks/configure_mce_environment.yml',
          description: 'Configure MCE CAPI/CAPA Environment',
          extra_vars: {},
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        console.error('❌ API returned error:', errorData);
        throw new Error(errorData.detail || errorData.message || 'Failed to start configuration');
      }

      const result = await response.json();
      console.log('📊 Configuration API response:', result);

      if (!result.job_id) {
        console.error('❌ No job_id in response:', result);
        throw new Error(result.message || result.detail || 'Failed to start configuration');
      }

      const jobId = result.job_id;
      console.log(`🔍 Polling job status for job_id: ${jobId}`);

      // Poll for job completion
      const pollJobStatus = async () => {
        const maxAttempts = 900; // 900 attempts = 15 minutes max wait (configuration can take a while)
        let attempts = 0;

        while (attempts < maxAttempts) {
          attempts++;
          console.log(`📡 Polling attempt ${attempts}/${maxAttempts}`);

          const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`));
          const jobData = await jobResponse.json();
          console.log(`📋 Job status:`, jobData);

          // Fetch logs regardless of status to show real-time output
          const logsResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}/logs`));
          const logsData = await logsResponse.json();
          const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';

          if (jobData.status === 'completed') {
            // Success - update with final logs
            const output = currentOutput || 'Configuration completed successfully';

            updateRecentOperationStatus(configureId, '✅ Configuration completed successfully!', output);
            setMceLastConfigured(new Date().toISOString());
            const successResults = {
              success: true,
              timestamp: new Date().toISOString(),
              output,
            };
            console.log('✅ Setting configuration results (success):', successResults);
            setConfigurationResults(successResults);
            setIsConfiguring(false);
            await refreshAllStatus();
            return;
          } else if (jobData.status === 'failed') {
            // Failure - update with error logs
            const output = currentOutput || (jobData.error || jobData.message || 'Configuration failed');

            updateRecentOperationStatus(configureId, '❌ Configuration failed', output);
            const failureResults = {
              success: false,
              timestamp: new Date().toISOString(),
              output,
            };
            console.log('❌ Setting configuration results (failure):', failureResults);
            setConfigurationResults(failureResults);
            setIsConfiguring(false);
            return;
          }

          // Still running - update with current logs every 5 seconds
          if (attempts % 5 === 0 && currentOutput) {
            updateRecentOperationStatus(configureId, '🚀 Configuring...', currentOutput);
            // Also update the inline display with real-time output
            setConfigurationResults({
              running: true,
              timestamp: new Date().toISOString(),
              output: currentOutput,
            });
          }

          // Wait and poll again
          await new Promise((resolve) => setTimeout(resolve, 1000)); // Wait 1 second
        }

        // Timeout
        throw new Error('Configuration timed out after 15 minutes');
      };

      await pollJobStatus();
    } catch (error) {
      console.error('Configuration error:', error);
      updateRecentOperationStatus(configureId, '❌ Configuration error', extractSafeErrorMessage(error));
      setConfigurationResults({
        success: false,
        timestamp: new Date().toISOString(),
        output: extractSafeErrorMessage(error),
      });
      setIsConfiguring(false);
    }
  };

  // Handle provision submit
  const handleProvisionSubmit = async (config) => {
    try {
      // Step 1: Generate YAML preview
      console.log('📄 Generating YAML preview...');
      const previewResponse = await fetch(buildApiUrl('/api/provisioning/generate-yaml'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config }),
      });

      const previewResult = await previewResponse.json();
      console.log('📄 Preview result:', previewResult);
      console.log('📄 yaml_content exists:', !!previewResult.yaml_content);
      console.log('📄 yaml_content length:', previewResult.yaml_content?.length || 0);

      if (!previewResult.success || !previewResult.yaml_content) {
        console.error('❌ Preview failed:', previewResult);
        throw new Error(previewResult.message || 'Failed to generate YAML preview');
      }

      // Step 2: Show YAML editor inline (not modal)
      setYamlEditorData({
        yaml_content: previewResult.yaml_content,
        cluster_name: config.clusterName,
        feature_type: 'rosa-hcp-provision',
        config: config, // Store config for later provisioning
        testSuite: selectedTestSuite, // Store test suite if provisioning from Feature Test Dashboard
      });
      setProvisionViewMode('yaml');

    } catch (error) {
      console.error('Preview generation error:', error);
      setToastMessage(`Failed to generate preview: ${extractSafeErrorMessage(error)}`); setToastType('error'); setTimeout(() => setToastMessage(''), 5000);
    }
  };

  // Handle delete
  const handleDelete = () => {
    console.log('Opening delete dialog...');
    // Navigate to delete page or open delete modal
  };

  // Handle reports
  const handleReports = () => {
    console.log('Opening reports...');
  };

  // Handle refresh
  const handleRefresh = async () => {
    await refreshAllStatus();
  };

  const handleUseEnvironmentCredentials = async (credentials) => {
    try {
      // Save the credentials to the backend
      const response = await fetch(buildApiUrl('/api/credentials'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ credentials }),
      });

      if (response.ok) {
        // Show success message
        setToastMessage(`Credentials set successfully for ${credentials.clusterName}! You can now verify or configure the environment.`); setToastType('success'); setTimeout(() => setToastMessage(''), 5000);

        // Refresh API status to reflect the new credentials
        await refreshAllStatus();
        // Force ActiveEnvironmentBanner to re-fetch credentials
        setCredentialsRefreshKey(prev => prev + 1);
      } else {
        const error = await response.json();
        setToastMessage(`Failed to save credentials: ${error.message || 'Unknown error'}`); setToastType('error'); setTimeout(() => setToastMessage(''), 5000);
      }
    } catch (error) {
      setToastMessage(`Failed to save credentials: ${error.message}`); setToastType('error'); setTimeout(() => setToastMessage(''), 5000);
    }
  };

  // Sidebar navigation handlers
  const sidebarHandlers = {
    onComponentsClick: () => setActiveSection('components'),
    onVerifyClick: () => setActiveSection('verify'),
    onConfigureClick: () => setActiveSection('configure'),
    onProvisionClick: () => {
      setProvisionResults(null); // Clear previous provision results
      setSelectedTestSuite(null); // Clear any test suite selection
      setActiveSection('provision');
    },
    onRosaHcpClustersClick: () => setActiveSection('rosa-hcp-clusters'),
    onResourcesClick: () => setActiveSection('resources'),
    onEnvironmentsClick: () => setActiveSection('environments'),
    onCredentialsClick: () => setActiveSection('credentials'),
    onAIAssistantClick: () => setActiveSection('ai-assistant'),
    onTerminalClick: () => setActiveSection('terminal'),
    onNotificationsClick: () => setActiveSection('notifications'),
    onRecentTasksClick: () => setActiveSection('recent-tasks'),
    onAWSUsageClick: () => navigate('/aws-usage'),
    onAgentDashboardClick: () => navigate('/agents'),
    onWorkflowsClick: () => setActiveSection('workflows'),
    onClusterActionsClick: () => setActiveSection('cluster-actions'),
    onOrchestratorClick: () => setActiveSection('orchestrator'),
  };

  // ============================================================================
  // Main Content Sections
  // ============================================================================

  const renderMainContent = () => {
    switch (activeSection) {
      case 'verify':
        return null;

      case 'configure':
        return (
          <div className="space-y-6">
            {/* Title */}
            <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">Configure CAPI/CAPA</h2>

            {/* Configuration Card */}
            <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
              <p className="text-gray-500 mb-6">
                Enable and configure CAPI/CAPA components on your MCE environment.
              </p>

              <div className="flex items-center gap-4">
                <button
                  onClick={handleConfigure}
                  disabled={apiLoading}
                  className={`px-5 py-2.5 text-sm font-semibold text-white rounded-lg flex items-center gap-2 transition-all shadow-sm hover:shadow-md ${
                    apiLoading
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700'
                  }`}
                >
                  {apiLoading ? (
                    <>
                      <div className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Configuring...
                    </>
                  ) : (
                    <>
                      <Cog6ToothIcon className="h-5 w-5" />
                      Start Configuration
                    </>
                  )}
                </button>

                {/* Last Configuration Info */}
                {mceLastConfigured && (
                  <div className="flex items-center gap-2 text-sm text-gray-500 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                    <CheckCircleIcon className="h-4 w-4 text-emerald-600" />
                    <span>Last configured: {new Date(mceLastConfigured).toLocaleString()}</span>
                    <span className="text-emerald-600 font-semibold">Completed</span>
                  </div>
                )}
              </div>
            </div>

            {/* Configuration Results or Loading */}
            {isConfiguring && !configurationResults && (
              <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
                    <ArrowPathIcon className="h-5 w-5 text-blue-600 animate-spin" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900">Running Configuration...</h3>
                </div>
                <p className="text-gray-500">Please wait while the playbook executes. This may take a minute or two.</p>
              </div>
            )}

            {configurationResults && (
              <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
                <div className="flex items-center gap-3 mb-4">
                  {configurationResults.running ? (
                    <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center">
                      <ArrowPathIcon className="h-5 w-5 text-blue-600 animate-spin" />
                    </div>
                  ) : configurationResults.success ? (
                    <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center">
                      <CheckCircleIcon className="h-5 w-5 text-emerald-600" />
                    </div>
                  ) : (
                    <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center">
                      <XCircleIcon className="h-5 w-5 text-red-600" />
                    </div>
                  )}
                  <h3 className="text-lg font-semibold text-gray-900">
                    {configurationResults.running ? 'Running Configuration...' : configurationResults.success ? 'Configuration Completed' : 'Configuration Failed'}
                  </h3>
                </div>

                {/* Output Display */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest">Playbook Output</h4>
                    <button
                      onClick={() => handleCopyOutput(configurationResults.output || 'No output available')}
                      className="px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                    >
                      {copySuccess || 'Copy'}
                    </button>
                  </div>
                  <div className="bg-gray-900 text-green-400 p-4 rounded-lg font-mono text-xs overflow-x-auto max-h-96 overflow-y-auto min-h-[100px] border border-gray-800">
                    <pre className="whitespace-pre-wrap">
                      {configurationResults.output || 'No output available'}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        );

      case 'provision':
        return (
          <div className="space-y-6">
            {/* Title */}
            <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">Provision ROSA HCP Cluster</h2>

            {/* Provisioning in Progress Banner */}
            {isProvisioning && !provisionResults && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
                    <div>
                      <h3 className="font-semibold text-blue-900">Provisioning in Progress</h3>
                      <p className="text-sm text-blue-700 mt-1">
                        Loading playbook output...
                      </p>
                    </div>
                  </div>
                  {provisionJobId && (
                    <button
                      onClick={async () => {
                        try {
                          await fetch(buildApiUrl(`/api/jobs/${provisionJobId}/cancel`), { method: 'POST' });
                          setIsProvisioning(false);
                          setProvisionJobId(null);
                          setProvisionResults({ success: false, timestamp: new Date().toISOString(), output: 'Provisioning cancelled by user', isRunning: false });
                          if (provisionOpId) updateRecentOperationStatus(provisionOpId, '🚫 Cancelled by user');
                        } catch (e) { console.error('Cancel failed:', e); }
                      }}
                      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Loading indicator while checking for running jobs */}
            {isCheckingProvisionJob ? (
              <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
                <div className="text-center py-12">
                  <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-cyan-600"></div>
                  <p className="mt-4 text-gray-600">Checking for running provision jobs...</p>
                </div>
              </div>
            ) : (
              /* Toggle between Form and YAML Editor - Only show if no provision results and not provisioning */
              !provisionResults && !isProvisioning && (
                provisionViewMode === 'form' ? (
                  /* Provision Form - Inline */
                  <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
                    <RosaProvisionModal
                      isOpen={true}
                      inline={true}
                      onClose={() => {}} // No close action needed for inline form
                      onSubmit={handleProvisionSubmit}
                      mceInfo={mceInfo}
                      testSuite={selectedTestSuite}
                    />
                  </div>
                ) : (
                /* YAML Editor - Inline */
                <YamlEditorModal
                  isOpen={true}
                  inline={true}
                  onClose={() => setProvisionViewMode('form')}
                  yamlData={yamlEditorData}
                  readOnly={false}
                  onProvision={async (editedYaml) => {
                  // Get the original config from yamlEditorData
                  const config = yamlEditorData?.config;
                  if (!config) {
                    setToastMessage('Configuration data not found'); setToastType('error'); setTimeout(() => setToastMessage(''), 5000);
                    return;
                  }

                  const provisionId = `provision-rosa-${Date.now()}`;
                  setProvisionOpId(provisionId);

                  // Check if this is from Feature Test Dashboard
                  const testSuite = yamlEditorData?.testSuite;
                  const titlePrefix = testSuite ? '🧪 Feature Test' : '🚀 Provision ROSA HCP';

                  try {
                    setIsProvisioning(true);

                    // Immediately show "Starting..." state to avoid blank form flash
                    setProvisionResults({
                      success: true,
                      timestamp: new Date().toISOString(),
                      output: `🚀 Starting provisioning for ${config.clusterName}...\n\nInitializing ROSA HCP cluster provisioning...\nCluster: ${config.clusterName}\nVersion: ${config.openShiftVersion}\nRegion: ${config.awsRegion}\n\nConnecting to backend...`,
                      isRunning: true,
                    });

                    addToRecent({
                      id: provisionId,
                      title: `${titlePrefix}: ${config.clusterName}`,
                      color: 'bg-green-600',
                      status: '🚀 Starting provisioning...',
                      environment: 'mce',
                      playbook: 'playbooks/create_rosa_hcp_cluster.yml',
                      output: `Initializing ROSA HCP cluster provisioning...\\nCluster: ${config.clusterName}\\nVersion: ${config.openShiftVersion}\\nRegion: ${config.awsRegion}`,
                    });

                    const response = await fetch(buildApiUrl(API_ENDPOINTS.ANSIBLE_RUN_PLAYBOOK), {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({
                        playbook: 'playbooks/create_rosa_hcp_cluster.yml',
                        description: `Provision ROSA HCP: ${config.clusterName}`,
                        extra_vars: config,
                        yaml_override: editedYaml,
                      }),
                    });

                    const result = await response.json();
                    console.log('📊 Provision API response:', result);

                    if (!result.success || !result.job_id) {
                      throw new Error(result.message || 'Failed to start provisioning');
                    }

                    const jobId = result.job_id;
                    setProvisionJobId(jobId);
                    console.log(`🔍 Polling job status for job_id: ${jobId}`);

                    // Close YAML editor immediately
                    setProvisionViewMode('form');

                    // Poll for job completion
                    const pollJobStatus = async () => {
                      const maxAttempts = 1800; // 1800 attempts = 30 minutes max (provisioning can take a while)
                      let attempts = 0;

                      while (attempts < maxAttempts) {
                        attempts++;
                        console.log(`📡 Polling attempt ${attempts}/${maxAttempts}`);

                        const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`));
                        const jobData = await jobResponse.json();
                        console.log(`📋 Job status:`, jobData);

                        // Fetch logs and agent stats
                        const [logsResponse, agentResponse] = await Promise.all([
                          fetch(buildApiUrl(`/api/jobs/${jobId}/logs`)),
                          fetch(buildApiUrl(`/api/jobs/${jobId}/agent-stats`)).catch(() => null),
                        ]);
                        const logsData = await logsResponse.json();
                        const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';
                        const agentData = agentResponse ? await agentResponse.json().catch(() => null) : null;
                        const agentStats = agentData?.agent_stats || null;

                        if (jobData.status === 'completed') {
                          // Success - update with final logs
                          const output = currentOutput || 'Provisioning completed successfully';

                          updateRecentOperationStatus(provisionId, '✅ ROSA HCP cluster provisioned successfully!', output, { agentStats });
                          const successResults = {
                            success: true,
                            timestamp: new Date().toISOString(),
                            output,
                            isRunning: false,
                            agentStats,
                          };
                          console.log('✅ Setting provision results (success):', successResults);
                          setProvisionResults(successResults);
                          setIsProvisioning(false);
                          setProvisionJobId(null);
                          await refreshAllStatus();
                          return;
                        } else if (jobData.status === 'failed') {
                          // Failure - update with error logs
                          const output = currentOutput || (jobData.error || jobData.message || 'Provisioning failed');

                          updateRecentOperationStatus(provisionId, '❌ Provisioning failed', output, { agentStats });
                          const failureResults = {
                            success: false,
                            timestamp: new Date().toISOString(),
                            output,
                            isRunning: false,
                            agentStats,
                          };
                          console.log('❌ Setting provision results (failure):', failureResults);
                          setProvisionResults(failureResults);
                          setIsProvisioning(false);
                          setProvisionJobId(null);
                          return;
                        }

                        // Still running - update with current logs every poll
                        if (currentOutput) {
                          updateRecentOperationStatus(provisionId, '🚀 Provisioning...', currentOutput, { agentStats });
                          setProvisionResults({
                            success: true,
                            timestamp: new Date().toISOString(),
                            output: currentOutput,
                            isRunning: true,
                            agentStats,
                          });
                        }

                        // Wait and poll again
                        await new Promise((resolve) => setTimeout(resolve, 2000)); // Wait 2 seconds
                      }

                      // Timeout
                      throw new Error('Provisioning timed out after 30 minutes');
                    };

                    await pollJobStatus();

                  } catch (error) {
                    console.error('Provisioning error:', error);
                    const errorMsg = extractSafeErrorMessage(error);
                    updateRecentOperationStatus(provisionId, '❌ Provisioning error', errorMsg);
                    setProvisionResults({
                      success: false,
                      timestamp: new Date().toISOString(),
                      output: errorMsg,
                      isRunning: false,
                    });
                    // Close YAML editor and show error output
                    setProvisionViewMode('form');
                  } finally {
                    setIsProvisioning(false);
                    setProvisionJobId(null);
                  }
                }}
              />
            )
              )
            )}

            {/* Provision Results Display - Inline Playbook Output */}
            {provisionResults && (
              <div className={`mt-6 rounded-lg border p-6 shadow-sm ${provisionResults.isRunning ? 'bg-blue-50 border-blue-200' : provisionResults.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    {provisionResults.isRunning ? (
                      <div className="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
                    ) : provisionResults.success ? (
                      <span className="text-2xl">✅</span>
                    ) : (
                      <span className="text-xl">❌</span>
                    )}
                    <h3 className="text-lg font-semibold text-gray-900">
                      {provisionResults.isRunning ? 'Provisioning in Progress' : provisionResults.success ? 'Provisioning Completed' : 'Provisioning Failed'}
                    </h3>
                  </div>
                  {provisionResults.isRunning && provisionJobId && (
                    <button
                      onClick={async () => {
                        try {
                          await fetch(buildApiUrl(`/api/jobs/${provisionJobId}/cancel`), { method: 'POST' });
                          setIsProvisioning(false);
                          setProvisionJobId(null);
                          setProvisionResults({ success: false, timestamp: new Date().toISOString(), output: provisionResults.output + '\n\n--- Provisioning cancelled by user ---', isRunning: false });
                          if (provisionOpId) updateRecentOperationStatus(provisionOpId, '🚫 Cancelled by user');
                        } catch (e) { console.error('Cancel failed:', e); }
                      }}
                      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium"
                    >
                      Cancel Provisioning
                    </button>
                  )}
                </div>

                {/* AI Agent Status */}
                {provisionResults.agentStats?.enabled && (
                  <div className={`mb-4 rounded-lg p-3 text-sm ${
                    provisionResults.agentStats.issues_detected > 0
                      ? 'bg-yellow-50 border border-yellow-300'
                      : 'bg-gray-50 border border-gray-200'
                  }`}>
                    <div className="flex items-center gap-4">
                      <span className="font-medium text-gray-700">
                        {provisionResults.agentStats.issues_detected > 0 ? '🤖' : '🛡️'} AI Agent
                        {provisionResults.isRunning ? ': Monitoring' : ': Summary'}
                      </span>
                      <span className={`${provisionResults.agentStats.issues_detected > 0 ? 'text-yellow-700' : 'text-gray-500'}`}>
                        Issues: {provisionResults.agentStats.issues_detected}
                      </span>
                      <span className={`${provisionResults.agentStats.interventions > 0 ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                        Interventions: {provisionResults.agentStats.interventions}
                      </span>
                      {provisionResults.agentStats.interventions > 0 && (
                        <span className="text-green-700 font-medium">
                          ✅ Agent auto-fixed {provisionResults.agentStats.interventions} issue(s)
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* Output Display */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest">Playbook Output</h4>
                    <button
                      onClick={() => handleCopyOutput(provisionResults.output || 'No output available')}
                      className="px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                    >
                      {copySuccess || 'Copy'}
                    </button>
                  </div>
                  <div className="bg-gray-900 text-gray-100 rounded-lg p-4 max-h-96 overflow-y-auto font-mono text-sm border border-gray-800" ref={el => {
                    if (el && provisionResults.isRunning) el.scrollTop = el.scrollHeight;
                  }}>
                    <pre className="whitespace-pre-wrap">
                      {provisionResults.output || 'No output available'}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        );

      case 'rosa-hcp-clusters':
        return (
          <div className="space-y-6">
            <RosaHcpClustersSection />
            <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">CAPA Resources</h2>
            <ResourcesViewer theme="mce" />
          </div>
        );

      case 'resources':
        return null;

      case 'environments':
        return (
          <div>
            <MCEEnvironmentSelector onUseCredentials={handleUseEnvironmentCredentials} />
          </div>
        );

      case 'credentials':
        return (
          <div className="space-y-6">
            {/* Title */}
            <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">Credentials & Environment</h2>

            {/* Credentials Section */}
            <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
              <CredentialsModal
                isOpen={true}
                inline={true}
                onClose={() => {}}
                theme="mce"
                onSave={() => {
                  refreshAllStatus();
                  setCredentialsRefreshKey(prev => prev + 1);
                  handleMceVerification();
                }}
              />
            </div>

            {/* Verification Section */}
            <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">Environment Verification</h3>
                <div className="flex items-center gap-3">
                  {mceLastVerified && (
                    <div className="flex items-center gap-2 text-sm text-gray-500 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                      <CheckCircleIcon className="h-4 w-4 text-emerald-600" />
                      <span>Last verified: {new Date(mceLastVerified).toLocaleString()}</span>
                      <span className="text-emerald-600 font-semibold">Passed</span>
                    </div>
                  )}
                  <button
                    onClick={handleMceVerification}
                    disabled={isVerifying}
                    className={`px-4 py-2 text-sm font-semibold text-white rounded-lg flex items-center gap-2 transition-all shadow-sm hover:shadow-md ${
                      isVerifying
                        ? 'bg-gray-400 cursor-not-allowed'
                        : 'bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700'
                    }`}
                  >
                    {isVerifying ? (
                      <>
                        <div className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        Verifying...
                      </>
                    ) : (
                      <>
                        <CheckCircleIcon className="h-4 w-4" />
                        Run Verification
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Components Lists - Side by Side */}
              <div className="grid grid-cols-2 gap-6">
                {/* CAPI/CAPA Components List */}
                <div>
                  <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">CAPI/CAPA</h3>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {(() => {
                      const capiComponents = mceFeatures
                        .filter(component =>
                          component.name === 'cluster-api' ||
                          component.name?.startsWith('cluster-api-provider-')
                        )
                        .sort((a, b) => (a.name || '').localeCompare(b.name || ''));

                      return capiComponents.length === 0 ? (
                        <div className="text-center py-8 bg-gray-50 border border-dashed border-gray-200 rounded-lg">
                          <p className="text-sm text-gray-500">No CAPI components configured</p>
                        </div>
                      ) : (
                        capiComponents.map((component, index) => (
                          <div
                            key={index}
                            className="flex items-center justify-between py-2 px-3 text-sm rounded-md hover:bg-gray-50 transition-colors"
                          >
                            <span className="truncate text-gray-700">{component.name}</span>
                            <span className={`ml-2 flex-shrink-0 ${component.enabled ? 'text-emerald-500' : 'text-red-400'}`}>
                              {component.enabled ? <CheckCircleIcon className="h-4 w-4" /> : <XCircleIcon className="h-4 w-4" />}
                            </span>
                          </div>
                        ))
                      );
                    })()}
                  </div>
                </div>

                {/* Hypershift Components List */}
                <div>
                  <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Hypershift</h3>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {(() => {
                      const hypershiftComponents = mceFeatures
                        .filter(component => component.name?.includes('hypershift'))
                        .sort((a, b) => (a.name || '').localeCompare(b.name || ''));

                      return hypershiftComponents.length === 0 ? (
                        <div className="text-center py-8 bg-gray-50 border border-dashed border-gray-200 rounded-lg">
                          <p className="text-sm text-gray-500">No Hypershift components configured</p>
                        </div>
                      ) : (
                        hypershiftComponents.map((component, index) => (
                          <div
                            key={index}
                            className="flex items-center justify-between py-2 px-3 text-sm rounded-md hover:bg-gray-50 transition-colors"
                          >
                            <span className="truncate text-gray-700">{component.name}</span>
                            <span className={`ml-2 flex-shrink-0 ${component.enabled ? 'text-emerald-500' : 'text-red-400'}`}>
                              {component.enabled ? <CheckCircleIcon className="h-4 w-4" /> : <XCircleIcon className="h-4 w-4" />}
                            </span>
                          </div>
                        ))
                      );
                    })()}
                  </div>
                </div>
              </div>

              {/* Verification Results */}
              {verificationResults && (
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <div className="flex items-center gap-2 mb-3">
                    {verificationResults.success === true ? (
                      <div className="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center">
                        <CheckCircleIcon className="h-4 w-4 text-emerald-600" />
                      </div>
                    ) : verificationResults.needsConfiguration ? (
                      <div className="w-6 h-6 rounded-full bg-amber-100 flex items-center justify-center">
                        <span className="text-xs">!</span>
                      </div>
                    ) : (
                      <div className="w-6 h-6 rounded-full bg-red-100 flex items-center justify-center">
                        <XCircleIcon className="h-4 w-4 text-red-600" />
                      </div>
                    )}
                    <span className="text-sm font-semibold text-gray-700">
                      {verificationResults.success === true
                        ? 'Verification Passed'
                        : verificationResults.needsConfiguration
                          ? 'Configuration Required'
                          : 'Verification Failed'}
                    </span>
                    <button
                      onClick={() => handleCopyOutput(verificationResults.output || 'No output available')}
                      className="ml-auto px-3 py-1 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                    >
                      {copySuccess || 'Copy Output'}
                    </button>
                  </div>
                  <div className="bg-gray-900 text-green-400 p-4 rounded-lg font-mono text-xs overflow-x-auto max-h-64 overflow-y-auto border border-gray-800">
                    <pre className="whitespace-pre-wrap">
                      {verificationResults.output || 'No output available'}
                    </pre>
                  </div>
                </div>
              )}
            </div>

            {/* Environments - collapsible, closed by default */}
            <div className="border border-gray-100 rounded-lg bg-white shadow-md">
              <button
                onClick={() => setShowEnvironments(prev => !prev)}
                className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 transition-colors"
              >
                <h3 className="text-lg font-semibold text-blue-900">MCE Environments</h3>
                <span className={`text-gray-400 transition-transform duration-200 ${showEnvironments ? 'rotate-180' : ''}`}>
                  &#9660;
                </span>
              </button>
              {showEnvironments && (
                <div className="border-t border-gray-200">
                  <MCEEnvironmentSelector onUseCredentials={handleUseEnvironmentCredentials} title="" />
                </div>
              )}
            </div>
          </div>
        );

      case 'workflows':
        return (
          <div className="space-y-6">
            <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">Workflow Builder</h2>
            <p className="text-gray-600">
              Chain playbooks into automated workflows. Drag from the palette, reorder steps, and run them as a pipeline.
            </p>
            <WorkflowBuilder />
          </div>
        );

      case 'cluster-actions':
        return (
          <ClusterActions />
        );

      case 'orchestrator':
        return (
          <WorkflowOrchestratorView />
        );

      case 'terminal':
        return (
          <div className="space-y-6">
            {/* Title */}
            <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">MCE Terminal</h2>

            <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
              <TerminalInline />
            </div>
          </div>
        );

      case 'notifications':
        return (
          <div className="space-y-6">
            {/* Title */}
            <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">Notification Settings</h2>

            <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
              <NotificationSettingsInline />
            </div>
          </div>
        );

      case 'recent-tasks':
        return (
          <div className="space-y-6">
            {/* Title */}
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">Task Summary</h2>
              {recentOps.recentOperations.filter((op) => op.environment === 'mce').length > 0 && (
                <button
                  onClick={() => recentOps.clearRecentOperations()}
                  className="px-4 py-2 bg-red-50 hover:bg-red-100 text-red-700 rounded-md transition-colors font-medium flex items-center gap-2 border border-red-200 text-sm"
                >
                  <TrashIcon className="h-4 w-4" />
                  Clear All
                </button>
              )}
            </div>

            <div className="bg-white rounded-lg shadow-md border border-gray-100 p-6">
              {recentOps.recentOperations.filter((op) => op.environment === 'mce').length === 0 ? (
                <div className="text-center py-12">
                  <ClockIcon className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-600">No tasks</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {recentOps.recentOperations.filter((op) => op.environment === 'mce').map((task, index) => (
                    <div key={task.id || index} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                      {/* Task Header */}
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center gap-3 flex-1">
                          <div className={`w-2 h-2 rounded-full ${task.color || 'bg-gray-400'}`}></div>
                          <div>
                            <h3 className="font-semibold text-gray-900">{task.title}</h3>
                            <p className="text-xs text-gray-500">
                              {task.timestamp ? new Date(task.timestamp).toLocaleString() : 'No timestamp'}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm">
                            {(() => {
                              const status = typeof task.status === 'object' ? task.status.status : task.status;
                              if (!status) return '⏳';
                              const statusStr = String(status);
                              if (statusStr.includes('✅') || statusStr.toLowerCase().includes('success')) return '✅';
                              if (statusStr.includes('❌') || statusStr.toLowerCase().includes('fail')) return '❌';
                              if (statusStr.includes('⚠️') || statusStr.toLowerCase().includes('warn')) return '⚠️';
                              return '⏳';
                            })()}
                          </span>
                        </div>
                      </div>

                      {/* Task Details */}
                      <div className="space-y-2 text-sm">
                        {task.environment && (
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-gray-700">Environment:</span>
                            <span className="text-gray-600">{task.environment}</span>
                          </div>
                        )}
                        {task.playbook && (
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-gray-700">Playbook:</span>
                            <span className="text-gray-600 font-mono text-xs">{task.playbook}</span>
                          </div>
                        )}
                        {task.status && (
                          <div className="flex items-start gap-2">
                            <span className="font-medium text-gray-700">Status:</span>
                            <span className="text-gray-600">
                              {typeof task.status === 'object' ? task.status.status : task.status}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* AI Agent Summary */}
                      {task.agentStats?.enabled && (
                        <div className={`mt-3 rounded-lg p-3 text-sm ${task.agentStats.issues_detected > 0 ? 'bg-yellow-50 border border-yellow-300' : 'bg-blue-50 border border-blue-200'}`}>
                          <div className="flex items-center gap-4 mb-2">
                            <span className="font-medium text-gray-700">
                              {task.agentStats.issues_detected > 0 ? '🤖' : '🛡️'} AI Agent: {task.agentStats.issues_detected > 0 ? 'Summary' : 'Monitoring'}
                            </span>
                            <span>Issues: {task.agentStats.issues_detected}</span>
                            <span>Interventions: {task.agentStats.interventions}</span>
                            {task.agentStats.interventions > 0 && (
                              <span className="text-green-700 font-medium">
                                Agent auto-fixed {task.agentStats.interventions} issue(s)
                              </span>
                            )}
                            {task.agentStats.issues_detected === 0 && (
                              <span className="text-blue-600">No issues detected</span>
                            )}
                          </div>
                          {task.agentStats.resource_details?.length > 0 && (
                            <div className="mt-2 pt-2 border-t border-yellow-200 space-y-1">
                              {task.agentStats.resource_details.map((detail, idx) => {
                                const statusIcon = detail.status === 'resolved' ? '✅'
                                  : detail.status === 'failed' ? '⚠️'
                                  : detail.status === 'detected' ? '🔍'
                                  : 'ℹ️';
                                const issueLabel = detail.issue_type?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Unknown';
                                return (
                                  <div key={idx} className="flex items-start gap-2 text-xs text-gray-600">
                                    <span className="flex-shrink-0">{statusIcon}</span>
                                    <div>
                                      <span className="font-medium text-gray-700">{detail.resource_key}</span>
                                      <span className="mx-1">&mdash;</span>
                                      <span>{issueLabel}</span>
                                      {detail.diagnosis && (
                                        <span className="text-gray-500 ml-1">({detail.diagnosis})</span>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Task Output */}
                      {task.output && (
                        <div className="mt-3">
                          <details className="bg-gray-50 rounded-lg">
                            <summary className="cursor-pointer p-3 font-medium text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
                              View Output
                            </summary>
                            <div className="p-3">
                              <div className="flex items-center justify-between mb-2">
                                <h4 className="text-xs font-medium text-gray-700">Task Output:</h4>
                                <button
                                  onClick={() => handleCopyOutput(typeof task.output === 'object' ? task.output.output : task.output)}
                                  className="px-2.5 py-1 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                                >
                                  {copySuccess || 'Copy'}
                                </button>
                              </div>
                              <div className="bg-gray-900 text-green-400 p-3 rounded-lg font-mono text-xs overflow-x-auto max-h-60 overflow-y-auto border border-gray-800">
                                <pre className="whitespace-pre-wrap">
                                  {typeof task.output === 'object' ? task.output.output : task.output}
                                </pre>
                              </div>
                            </div>
                          </details>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );

      default:
        return (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent mb-4">
              {activeSection.charAt(0).toUpperCase() + activeSection.slice(1)}
            </h2>
            <p className="text-gray-600">Content for {activeSection} section coming soon...</p>
          </div>
        );
    }
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* CAPA Sidebar */}
      <CapaSidebar
        {...sidebarHandlers}
        activeSection={activeSection}
      />

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto">
        {/* Page Header with Blue Gradient */}
        <div className="bg-gradient-to-r from-blue-600 to-cyan-500 text-white px-6 py-4 shadow-lg flex items-center gap-4 h-[72px]">
          <h1 className="text-2xl font-bold leading-tight tracking-tight">MCE Environment</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveSection('terminal')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeSection === 'terminal'
                  ? 'bg-white/30'
                  : 'bg-white/10 hover:bg-white/20'
              }`}
              title="Terminal"
            >
              <span>💻</span>
              <span>Terminal</span>
            </button>
            <button
              onClick={() => setActiveSection('notifications')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeSection === 'notifications'
                  ? 'bg-white/30'
                  : 'bg-white/10 hover:bg-white/20'
              }`}
              title="Notifications"
            >
              <span>🔔</span>
              <span>Notifications</span>
            </button>
            <button
              onClick={() => navigate('/agents')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-white/10 hover:bg-white/20"
              title="AI Agent Pipeline"
            >
              <span>🧠</span>
              <span>AI Agents</span>
            </button>
            <button
              onClick={() => navigate('/aws-usage')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-white/10 hover:bg-white/20"
              title="AWS Usage"
            >
              <span>☁️</span>
              <span>AWS Usage</span>
            </button>
          </div>
        </div>

        <div className="p-6">
          {/* Active Environment Banner */}
          <ActiveEnvironmentBanner
            key={credentialsRefreshKey}
            verificationTimestamp={mceLastVerified}
          />

          {/* Toast Message */}
          {toastMessage && (
            <div className={`mb-4 p-4 rounded-lg border ${
              toastType === 'success' ? 'bg-green-50 border-green-200 text-green-800' :
              toastType === 'error' ? 'bg-red-50 border-red-200 text-red-800' :
              'bg-blue-50 border-blue-200 text-blue-800'
            }`}>
              <div className="flex items-center justify-between">
                <span className="text-sm">{toastMessage}</span>
                <button onClick={() => setToastMessage('')} className="text-sm font-medium ml-4">Dismiss</button>
              </div>
            </div>
          )}

          {/* Main Content */}
          {renderMainContent()}
        </div>
      </div>

      {/* Modals */}
      <YamlEditorModal
        isOpen={showYamlEditorModal}
        onClose={() => setShowYamlEditorModal(false)}
        yamlData={yamlEditorData}
        readOnly={false}
        onProvision={async (editedYaml) => {
          // Close the modal first
          setShowYamlEditorModal(false);

          // Get the original config from yamlEditorData
          const config = yamlEditorData?.config;
          if (!config) {
            setToastMessage('Configuration data not found'); setToastType('error'); setTimeout(() => setToastMessage(''), 5000);
            return;
          }

          const provisionId = `provision-rosa-${Date.now()}`;

          // Check if this is from Feature Test Dashboard
          const testSuite = yamlEditorData?.testSuite;
          const titlePrefix = testSuite ? '🧪 Feature Test' : '🚀 Provision ROSA HCP';

          try {
            setIsProvisioning(true);

            // Immediately show "Starting..." state to avoid blank form flash
            setProvisionResults({
              success: true,
              timestamp: new Date().toISOString(),
              output: `🚀 Starting provisioning for ${config.clusterName}...\n\nInitializing ROSA HCP cluster provisioning...\nCluster: ${config.clusterName}\nVersion: ${config.openShiftVersion}\nRegion: ${config.awsRegion}\n\nConnecting to backend...`,
            });

            addToRecent({
              id: provisionId,
              title: `${titlePrefix}: ${config.clusterName}`,
              color: 'bg-green-600',
              status: '🚀 Starting provisioning...',
              environment: 'mce',
              playbook: 'playbooks/create_rosa_hcp_cluster.yml',
              output: `Initializing ROSA HCP cluster provisioning...\nCluster: ${config.clusterName}\nVersion: ${config.openShiftVersion}\nRegion: ${config.awsRegion}`,
            });

            const response = await fetch(buildApiUrl(API_ENDPOINTS.ANSIBLE_RUN_PLAYBOOK), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                playbook: 'playbooks/create_rosa_hcp_cluster.yml',
                description: `Provision ROSA HCP: ${config.clusterName}`,
                extra_vars: config,
                yaml_override: editedYaml, // Use edited YAML if user modified it
              }),
            });

            const result = await response.json();
            console.log('📊 Provision API response:', result);

            if (!result.success || !result.job_id) {
              throw new Error(result.message || 'Failed to start provisioning');
            }

            const jobId = result.job_id;
            console.log(`🔍 Polling job status for job_id: ${jobId}`);

            // Poll for job completion
            const pollJobStatus = async () => {
              const maxAttempts = 1800; // 1800 attempts = 30 minutes max
              let attempts = 0;

              while (attempts < maxAttempts) {
                attempts++;
                console.log(`📡 Polling attempt ${attempts}/${maxAttempts}`);

                const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`));
                const jobData = await jobResponse.json();
                console.log(`📋 Job status:`, jobData);

                // Fetch logs and agent stats
                const [logsResponse, agentResponse2] = await Promise.all([
                  fetch(buildApiUrl(`/api/jobs/${jobId}/logs`)),
                  fetch(buildApiUrl(`/api/jobs/${jobId}/agent-stats`)).catch(() => null),
                ]);
                const logsData = await logsResponse.json();
                const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';
                const agentData2 = agentResponse2 ? await agentResponse2.json().catch(() => null) : null;
                const agentStats2 = agentData2?.agent_stats || null;

                if (jobData.status === 'completed') {
                  // Success - update with final logs
                  const output = currentOutput || 'Provisioning completed successfully';

                  updateRecentOperationStatus(provisionId, '✅ ROSA HCP cluster provisioned successfully!', output, { agentStats: agentStats2 });
                  const successResults = {
                    success: true,
                    timestamp: new Date().toISOString(),
                    output,
                    agentStats: agentStats2,
                  };
                  console.log('✅ Setting provision results (success):', successResults);
                  setProvisionResults(successResults);
                  setIsProvisioning(false);
                  await refreshAllStatus();
                  return;
                } else if (jobData.status === 'failed') {
                  // Failure - update with error logs
                  const output = currentOutput || (jobData.error || jobData.message || 'Provisioning failed');

                  updateRecentOperationStatus(provisionId, '❌ Provisioning failed', output, { agentStats: agentStats2 });
                  const failureResults = {
                    success: false,
                    timestamp: new Date().toISOString(),
                    output,
                    agentStats: agentStats2,
                  };
                  console.log('❌ Setting provision results (failure):', failureResults);
                  setProvisionResults(failureResults);
                  setIsProvisioning(false);
                  return;
                }

                // Still running - update with current logs every 5 seconds
                if (attempts % 5 === 0 && currentOutput) {
                  updateRecentOperationStatus(provisionId, '🚀 Provisioning...', currentOutput, { agentStats: agentStats2 });
                  setProvisionResults({
                    success: true,
                    timestamp: new Date().toISOString(),
                    output: currentOutput,
                    agentStats: agentStats2,
                  });
                }

                // Wait and poll again
                await new Promise((resolve) => setTimeout(resolve, 1000)); // Wait 1 second
              }

              // Timeout
              throw new Error('Provisioning timed out after 30 minutes');
            };

            await pollJobStatus();

          } catch (error) {
            console.error('Provisioning error:', error);
            const errorMsg = extractSafeErrorMessage(error);
            updateRecentOperationStatus(provisionId, '❌ Provisioning error', errorMsg);
            setProvisionResults({
              success: false,
              timestamp: new Date().toISOString(),
              output: errorMsg,
            });
          } finally {
            setIsProvisioning(false);
          }
        }}
      />
    </div>
  );
};

export default CAPADashboardContent;
