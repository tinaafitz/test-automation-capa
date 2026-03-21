import React, { useState } from 'react';
import {
  ExclamationTriangleIcon,
  SparklesIcon,
  MagnifyingGlassIcon,
  WrenchIcon
} from '@heroicons/react/24/outline';
import AgentButton from './AgentButton';
import AgentResultsModal from './AgentResultsModal';
import AgentStatusBadge from './AgentStatusBadge';
import useAgents from '../../hooks/useAgents';

/**
 * ProvisionFailureAgentPanel - Intelligent failure analysis panel
 *
 * Displays when cluster provision fails and offers AI agent assistance:
 * - Explore Agent: Investigate failure patterns in codebase
 * - General Agent: Diagnose issue and suggest fixes
 * - Auto-fix: Apply automated corrections
 *
 * Auto-starts diagnosis when autoAnalyze=true
 *
 * Usage:
 * <ProvisionFailureAgentPanel
 *   clusterName="demo-cluster"
 *   errorMessage="IAM role not found"
 *   errorLogs="[full error logs]"
 *   autoAnalyze={true}  // Automatically start AI analysis
 *   onRetry={() => retryProvisioning()}
 * />
 */
const ProvisionFailureAgentPanel = ({
  clusterName,
  errorMessage,
  errorLogs = "",
  autoAnalyze = true,  // Auto-start analysis by default
  onRetry = null,
  onClose = null,
  addToRecentOperations = null  // Function to add AI actions to task log
}) => {
  const isDeletion = /delet/i.test(errorMessage);
  const actionLabel = isDeletion ? 'Deletion' : 'Provisioning';
  const {
    spawnExploreAgent,
    spawnGeneralAgent,
    loading,
    error
  } = useAgents();

  const [agentResults, setAgentResults] = useState(null);
  const [showResults, setShowResults] = useState(false);
  const [currentAgentType, setCurrentAgentType] = useState(null);
  const [agentStatus, setAgentStatus] = useState(null);
  const [autoAnalysisStarted, setAutoAnalysisStarted] = useState(false);
  const [autoFixApplied, setAutoFixApplied] = useState(false);

  /**
   * Investigate failure with Explore agent
   */
  const handleInvestigateFailure = async () => {
    setAgentStatus('spawning');
    setCurrentAgentType('explore');

    try {
      const result = await spawnExploreAgent(
        `Investigate why ROSA HCP cluster "${clusterName}" provisioning failed with error: ${errorMessage}`,
        'very thorough',
        {
          cluster_name: clusterName,
          error_message: errorMessage,
          error_logs: errorLogs.substring(0, 1000) // Truncate for context
        }
      );

      setAgentStatus('completed');
      setAgentResults(result);
      setShowResults(true);
    } catch (err) {
      console.error('Failed to spawn Explore agent:', err);
      setAgentStatus('failed');
    }
  };

  /**
   * Diagnose and fix with General agent
   */
  const handleDiagnoseAndFix = async () => {
    setAgentStatus('spawning');
    setCurrentAgentType('general');

    // Log AI analysis start to task summary
    if (addToRecentOperations) {
      addToRecentOperations({
        id: `ai-analysis-${Date.now()}`,
        title: `🤖 ${actionLabel} Failed: ${clusterName}`,
        color: 'bg-purple-600',
        status: `🔍 AI investigating ${actionLabel.toLowerCase()} failure...`,
        environment: 'mce',
        output: `AI Agent started analyzing failure for: ${clusterName}\n\nError: ${errorMessage}\n\nAI is searching codebase for similar issues and generating fixes...`,
      });
    }

    try {
      const result = await spawnGeneralAgent(
        `Diagnose and fix ROSA HCP cluster "${clusterName}" provisioning failure`,
        'fix',
        {
          cluster_name: clusterName,
          error_message: errorMessage,
          error_logs: errorLogs.substring(0, 1000),
          requested_action: 'diagnose_and_fix'
        }
      );

      setAgentStatus('completed');
      setAgentResults(result);
      setShowResults(true);

      // Log AI analysis completion to task summary
      if (addToRecentOperations) {
        const diagnosisText = result.diagnosis || result.findings?.[0] || 'AI analysis completed';
        const fixCount = result.automated_fixes?.length || 0;
        addToRecentOperations({
          id: `ai-analysis-complete-${Date.now()}`,
          title: `✅ AI Analysis Complete: ${clusterName}`,
          color: 'bg-green-600',
          status: `✅ Found ${fixCount} potential fix${fixCount !== 1 ? 'es' : ''}`,
          environment: 'mce',
          output: `AI Analysis Results:\n\nDiagnosis: ${diagnosisText}\n\n${fixCount > 0 ? `AI will automatically apply the first fix...` : 'No automated fixes available.'}`,
        });
      }
    } catch (err) {
      console.error('Failed to spawn General agent:', err);
      setAgentStatus('failed');

      // Log AI failure to task summary
      if (addToRecentOperations) {
        addToRecentOperations({
          id: `ai-analysis-failed-${Date.now()}`,
          title: `❌ ${actionLabel} Failed: ${clusterName}`,
          color: 'bg-red-600',
          status: `❌ ${actionLabel} failed - AI agent encountered an error`,
          environment: 'mce',
          output: `AI Analysis Error:\n\n${err.message || 'Unknown error occurred'}`,
        });
      }
    }
  };

  /**
   * Apply automated fix
   */
  const handleApplyFix = async (fix, index) => {
    console.log('Applying automated fix:', fix);
    // TODO: Integrate with backend to apply fix
    // This would trigger a retry with corrections
    if (onRetry) {
      onRetry({ automated_fix: fix, fix_index: index });
    }
    setShowResults(false);
  };

  /**
   * Auto-start analysis when panel mounts
   */
  React.useEffect(() => {
    if (autoAnalyze && !autoAnalysisStarted && !loading && !agentResults) {
      setAutoAnalysisStarted(true);
      handleDiagnoseAndFix();
    }
  }, [autoAnalyze, autoAnalysisStarted, loading, agentResults]);

  /**
   * Auto-apply fixes when agent completes with automated fixes
   */
  React.useEffect(() => {
    if (agentResults && agentStatus === 'completed' && agentResults.automated_fixes?.length > 0 && !autoFixApplied) {
      console.log('🤖 Auto-applying first automated fix:', agentResults.automated_fixes[0]);
      setAutoFixApplied(true);

      // Log auto-fix application to task summary
      if (addToRecentOperations) {
        const fix = agentResults.automated_fixes[0];
        addToRecentOperations({
          id: `ai-auto-fix-${Date.now()}`,
          title: `🤖 AI Auto-Applying Fix: ${clusterName}`,
          color: 'bg-blue-600',
          status: '🔧 Automatically applying AI-generated fix...',
          environment: 'mce',
          output: `AI is automatically applying the following fix:\n\n${typeof fix === 'string' ? fix : JSON.stringify(fix, null, 2)}\n\nRetrying operation with fix applied...`,
        });
      }

      // Apply the first fix automatically
      handleApplyFix(agentResults.automated_fixes[0], 0);
    }
  }, [agentResults, agentStatus, autoFixApplied]);

  return (
    <>
      <div className="bg-gradient-to-r from-red-50 to-orange-50 border border-red-200 rounded-lg p-6 shadow-md">
        {/* Header */}
        <div className="flex items-start gap-4 mb-4">
          <div className="flex-shrink-0">
            <div className="p-3 bg-red-100 rounded-lg">
              <ExclamationTriangleIcon className="h-8 w-8 text-red-600" />
            </div>
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-gray-900 mb-1">
              Provisioning Failed: {clusterName}
            </h3>
            <p className="text-sm text-red-700 mb-3">
              {errorMessage}
            </p>

            {/* Agent Status Badge */}
            {agentStatus && (
              <div className="mb-3 flex items-center gap-2">
                <AgentStatusBadge status={agentStatus} />
                {(agentStatus === 'spawning' || agentStatus === 'running') && (
                  <span className="text-sm text-purple-700">
                    AI is analyzing the failure...
                  </span>
                )}
                {agentStatus === 'completed' && agentResults && !autoFixApplied && (
                  <button
                    onClick={() => setShowResults(true)}
                    className="text-sm text-blue-600 hover:text-blue-800 underline font-medium"
                  >
                    View AI Analysis Results
                  </button>
                )}
                {autoFixApplied && (
                  <span className="text-sm text-green-700 font-medium">
                    🤖 AI automatically applied fix and retrying...
                  </span>
                )}
              </div>
            )}

            {/* Error Display */}
            {error && (
              <div className="bg-red-100 border border-red-300 rounded p-3 mb-4">
                <p className="text-sm text-red-800">
                  <strong>Agent Error:</strong> {error}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* AI Agent Actions - Only show if auto-analysis is disabled or failed */}
        {(!autoAnalyze || agentStatus === 'failed') && (
          <div className="border-t border-red-200 pt-4">
            <div className="flex items-center gap-2 mb-3">
              <SparklesIcon className="h-5 w-5 text-purple-600" />
              <h4 className="text-sm font-semibold text-gray-900">
                Let AI help investigate and fix this issue
              </h4>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Investigate Button */}
              <AgentButton
                onClick={handleInvestigateFailure}
                label="Investigate Failure"
                icon={<MagnifyingGlassIcon className="h-5 w-5" />}
                variant="primary"
                loading={loading && currentAgentType === 'explore'}
                disabled={loading}
              />

              {/* Diagnose & Fix Button */}
              <AgentButton
                onClick={handleDiagnoseAndFix}
                label="Diagnose & Suggest Fixes"
                icon={<WrenchIcon className="h-5 w-5" />}
                variant="primary"
                loading={loading && currentAgentType === 'general'}
                disabled={loading}
              />
            </div>

            {/* Help Text */}
            <p className="text-xs text-gray-600 mt-3">
              AI agents can search the codebase for similar issues, analyze error patterns,
              and suggest automated fixes to resolve this provisioning failure.
            </p>
          </div>
        )}

        {/* Auto-analysis results summary - Show inline when completed */}
        {autoAnalyze && agentStatus === 'completed' && agentResults && !showResults && (
          <div className="border-t border-red-200 pt-4">
            <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <SparklesIcon className="h-5 w-5 text-purple-600" />
                <h4 className="text-sm font-semibold text-gray-900">
                  AI Analysis Complete
                </h4>
              </div>
              <p className="text-sm text-gray-700 mb-3">
                {agentResults.diagnosis || agentResults.findings?.[0] || 'AI has analyzed the failure and identified potential solutions.'}
              </p>
              <button
                onClick={() => setShowResults(true)}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium"
              >
                View Full Analysis & Fixes
              </button>
            </div>
          </div>
        )}

        {/* Manual Actions */}
        {(onRetry || onClose) && (
          <div className="border-t border-red-200 pt-4 mt-4">
            <div className="flex items-center gap-3">
              {onRetry && (
                <button
                  onClick={() => onRetry()}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
                >
                  Retry Provisioning
                </button>
              )}
              {onClose && (
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors text-sm font-medium"
                >
                  Close
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Agent Results Modal */}
      {showResults && agentResults && (
        <AgentResultsModal
          isOpen={showResults}
          onClose={() => setShowResults(false)}
          agentType={currentAgentType}
          results={agentResults}
          onApplyFix={handleApplyFix}
          onRetry={currentAgentType === 'explore' ? handleDiagnoseAndFix : null}
        />
      )}
    </>
  );
};

export default ProvisionFailureAgentPanel;
