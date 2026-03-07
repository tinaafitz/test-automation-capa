import React, { useState } from 'react';
import {
  LightBulbIcon,
  SparklesIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline';
import AgentButton from './AgentButton';
import AgentResultsModal from './AgentResultsModal';
import AgentStatusBadge from './AgentStatusBadge';
import useAgents from '../../hooks/useAgents';

/**
 * ConfigurationPlannerPanel - AI-powered configuration planning
 *
 * Helps users plan optimal cluster configurations using Plan agent:
 * - Validates feature compatibility
 * - Recommends best practices
 * - Checks for known issues
 * - Suggests optimal settings
 *
 * Usage:
 * <ConfigurationPlannerPanel
 *   requirements={{
 *     openshift_version: "4.14",
 *     region: "us-east-1",
 *     fips: true,
 *     log_forwarding: true
 *   }}
 *   onApplyConfiguration={(config) => applyToForm(config)}
 * />
 */
const ConfigurationPlannerPanel = ({
  requirements = {},
  onApplyConfiguration = null,
  compact = false
}) => {
  const {
    spawnPlanAgent,
    loading,
    error
  } = useAgents();

  const [agentResults, setAgentResults] = useState(null);
  const [showResults, setShowResults] = useState(false);
  const [agentStatus, setAgentStatus] = useState(null);

  /**
   * Generate configuration plan with Plan agent
   */
  const handlePlanConfiguration = async () => {
    setAgentStatus('spawning');

    // Build prompt from requirements
    const prompt = buildPlanPrompt(requirements);

    try {
      const result = await spawnPlanAgent(prompt, requirements);

      setAgentStatus('completed');
      setAgentResults(result);
      setShowResults(true);
    } catch (err) {
      console.error('Failed to spawn Plan agent:', err);
      setAgentStatus('failed');
    }
  };

  /**
   * Build plan prompt from requirements
   */
  const buildPlanPrompt = (req) => {
    const parts = ['Plan an optimal ROSA HCP cluster configuration'];

    if (req.openshift_version) {
      parts.push(`with OpenShift ${req.openshift_version}`);
    }
    if (req.region) {
      parts.push(`in region ${req.region}`);
    }
    if (req.fips) {
      parts.push('with FIPS mode enabled');
    }
    if (req.log_forwarding) {
      parts.push('with log forwarding to CloudWatch');
    }
    if (req.multi_az) {
      parts.push('across multiple availability zones');
    }

    return parts.join(' ');
  };

  /**
   * Apply configuration to form
   */
  const handleApplyConfiguration = (config) => {
    if (onApplyConfiguration) {
      onApplyConfiguration(config);
    }
    setShowResults(false);
  };

  // Compact view (for embedding in forms)
  if (compact) {
    return (
      <>
        <div className="bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <LightBulbIcon className="h-6 w-6 text-purple-600 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-900 mb-2">
                Need help planning your configuration?
              </p>
              {agentStatus && (
                <div className="mb-2">
                  <AgentStatusBadge status={agentStatus} size="small" />
                </div>
              )}
              <AgentButton
                onClick={handlePlanConfiguration}
                label="Get AI Recommendations"
                icon={<SparklesIcon className="h-4 w-4" />}
                variant="primary"
                size="small"
                loading={loading}
              />
            </div>
          </div>
        </div>

        {showResults && agentResults && (
          <AgentResultsModal
            isOpen={showResults}
            onClose={() => setShowResults(false)}
            agentType="plan"
            results={agentResults}
            onRetry={handlePlanConfiguration}
          />
        )}
      </>
    );
  }

  // Full view (standalone panel)
  return (
    <>
      <div className="bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-lg p-6 shadow-md">
        {/* Header */}
        <div className="flex items-start gap-4 mb-4">
          <div className="flex-shrink-0">
            <div className="p-3 bg-purple-100 rounded-lg">
              <LightBulbIcon className="h-8 w-8 text-purple-600" />
            </div>
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-gray-900 mb-1">
              AI Configuration Planner
            </h3>
            <p className="text-sm text-gray-700 mb-3">
              Get intelligent recommendations for your cluster configuration
            </p>

            {/* Agent Status Badge */}
            {agentStatus && (
              <div className="mb-3">
                <AgentStatusBadge status={agentStatus} />
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

        {/* Requirements Summary */}
        {Object.keys(requirements).length > 0 && (
          <div className="bg-white border border-purple-200 rounded-lg p-4 mb-4">
            <h4 className="text-sm font-semibold text-gray-900 mb-2">
              Current Requirements:
            </h4>
            <ul className="space-y-1">
              {requirements.openshift_version && (
                <li className="flex items-center gap-2 text-sm text-gray-700">
                  <CheckCircleIcon className="h-4 w-4 text-green-600" />
                  OpenShift {requirements.openshift_version}
                </li>
              )}
              {requirements.region && (
                <li className="flex items-center gap-2 text-sm text-gray-700">
                  <CheckCircleIcon className="h-4 w-4 text-green-600" />
                  Region: {requirements.region}
                </li>
              )}
              {requirements.fips && (
                <li className="flex items-center gap-2 text-sm text-gray-700">
                  <CheckCircleIcon className="h-4 w-4 text-green-600" />
                  FIPS mode enabled
                </li>
              )}
              {requirements.log_forwarding && (
                <li className="flex items-center gap-2 text-sm text-gray-700">
                  <CheckCircleIcon className="h-4 w-4 text-green-600" />
                  Log forwarding to CloudWatch
                </li>
              )}
            </ul>
          </div>
        )}

        {/* Plan Configuration Button */}
        <AgentButton
          onClick={handlePlanConfiguration}
          label="Generate Configuration Plan"
          icon={<SparklesIcon className="h-5 w-5" />}
          variant="primary"
          loading={loading}
          className="w-full"
        />

        {/* Help Text */}
        <p className="text-xs text-gray-600 mt-3">
          The AI will analyze your requirements, check feature compatibility,
          validate settings, and recommend the optimal configuration for your cluster.
        </p>
      </div>

      {/* Agent Results Modal */}
      {showResults && agentResults && (
        <AgentResultsModal
          isOpen={showResults}
          onClose={() => setShowResults(false)}
          agentType="plan"
          results={agentResults}
          onRetry={handlePlanConfiguration}
        />
      )}
    </>
  );
};

export default ConfigurationPlannerPanel;
