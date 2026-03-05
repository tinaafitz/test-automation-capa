import React from 'react';
import {
  XMarkIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';

/**
 * AgentResultsModal - Modal for displaying agent analysis results
 *
 * Features:
 * - Structured display of agent findings
 * - Recommendations with action buttons
 * - Files examined list
 * - Auto-fix suggestions
 * - Copy to clipboard functionality
 */
const AgentResultsModal = ({
  isOpen,
  onClose,
  agentType = "explore", // explore, plan, general
  results = {},
  onApplyFix = null,
  onRetry = null
}) => {
  if (!isOpen) return null;

  const {
    findings = [],
    recommendations = [],
    files_examined = [],
    plan = {},
    configuration = {},
    validation_results = [],
    warnings = [],
    diagnosis = "",
    root_cause = "",
    fix_recommendations = [],
    automated_fixes = [],
    next_steps = [],
    raw_output = ""
  } = results;

  // Get title based on agent type
  const getTitle = () => {
    switch (agentType) {
      case 'explore':
        return '🔍 Codebase Analysis Results';
      case 'plan':
        return '📋 Configuration Plan';
      case 'general':
        return '🔧 Troubleshooting Results';
      default:
        return '✨ Agent Results';
    }
  };

  // Render section with items
  const renderSection = (title, items, icon) => {
    if (!items || items.length === 0) return null;

    return (
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          {icon}
          <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        </div>
        <ul className="space-y-2">
          {items.map((item, index) => (
            <li key={index} className="flex items-start gap-2">
              <span className="text-blue-600 mt-1">•</span>
              <span className="text-gray-700 flex-1">{item}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  // Render text section
  const renderTextSection = (title, content, icon) => {
    if (!content) return null;

    return (
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          {icon}
          <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        </div>
        <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
          <p className="text-gray-700 whitespace-pre-wrap">{content}</p>
        </div>
      </div>
    );
  };

  // Render automated fixes with action buttons
  const renderAutomatedFixes = () => {
    if (!automated_fixes || automated_fixes.length === 0) return null;

    return (
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <SparklesIcon className="h-5 w-5 text-purple-600" />
          <h3 className="text-lg font-semibold text-gray-900">Automated Fixes Available</h3>
        </div>
        <div className="space-y-3">
          {automated_fixes.map((fix, index) => (
            <div key={index} className="bg-purple-50 rounded-lg p-4 border border-purple-200">
              <p className="text-gray-700 mb-3">{fix}</p>
              {onApplyFix && (
                <button
                  onClick={() => onApplyFix(fix, index)}
                  className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium"
                >
                  Apply This Fix
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-2xl font-bold text-gray-900">{getTitle()}</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <XMarkIcon className="h-6 w-6 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Explore Agent Results */}
          {agentType === 'explore' && (
            <>
              {renderSection('Key Findings', findings, <InformationCircleIcon className="h-5 w-5 text-blue-600" />)}
              {renderSection('Recommendations', recommendations, <CheckCircleIcon className="h-5 w-5 text-green-600" />)}
              {renderSection('Files Examined', files_examined, <InformationCircleIcon className="h-5 w-5 text-gray-600" />)}
            </>
          )}

          {/* Plan Agent Results */}
          {agentType === 'plan' && (
            <>
              {renderTextSection('Implementation Plan', typeof plan === 'string' ? plan : JSON.stringify(plan, null, 2), <CheckCircleIcon className="h-5 w-5 text-green-600" />)}
              {renderTextSection('Recommended Configuration', typeof configuration === 'string' ? configuration : JSON.stringify(configuration, null, 2), <InformationCircleIcon className="h-5 w-5 text-blue-600" />)}
              {renderSection('Validation Results', validation_results, <CheckCircleIcon className="h-5 w-5 text-green-600" />)}
              {renderSection('Warnings', warnings, <ExclamationTriangleIcon className="h-5 w-5 text-yellow-600" />)}
            </>
          )}

          {/* General Agent Results */}
          {agentType === 'general' && (
            <>
              {renderTextSection('Diagnosis', diagnosis, <InformationCircleIcon className="h-5 w-5 text-blue-600" />)}
              {renderTextSection('Root Cause', root_cause, <ExclamationTriangleIcon className="h-5 w-5 text-red-600" />)}
              {renderSection('Fix Recommendations', fix_recommendations, <CheckCircleIcon className="h-5 w-5 text-green-600" />)}
              {renderAutomatedFixes()}
              {renderSection('Next Steps', next_steps, <InformationCircleIcon className="h-5 w-5 text-blue-600" />)}
            </>
          )}

          {/* Raw Output (collapsible) */}
          {raw_output && (
            <details className="mt-6">
              <summary className="cursor-pointer text-sm font-medium text-gray-600 hover:text-gray-900 mb-2">
                View Full Agent Response
              </summary>
              <div className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto">
                <pre className="text-xs font-mono whitespace-pre-wrap">{raw_output}</pre>
              </div>
            </details>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 bg-gray-50">
          {onRetry && (
            <button
              onClick={onRetry}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              Run Analysis Again
            </button>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default AgentResultsModal;
