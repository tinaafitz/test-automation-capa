import React, { useState } from 'react';
import { SparklesIcon } from '@heroicons/react/24/outline';

/**
 * AgentButton - Button component for triggering agent actions
 *
 * Features:
 * - Clean gradient design
 * - Loading state with spinner
 * - Disabled state handling
 * - Customizable icon and text
 */
const AgentButton = ({
  onClick,
  label = "Ask AI Agent",
  icon = <SparklesIcon className="h-5 w-5" />,
  disabled = false,
  loading = false,
  variant = "primary", // primary, secondary, danger
  size = "medium", // small, medium, large
  className = ""
}) => {
  const [isHovered, setIsHovered] = useState(false);

  // Variant styles
  const variantStyles = {
    primary: "bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white",
    secondary: "bg-gradient-to-r from-gray-600 to-gray-700 hover:from-gray-700 hover:to-gray-800 text-white",
    danger: "bg-gradient-to-r from-red-600 to-orange-600 hover:from-red-700 hover:to-orange-700 text-white"
  };

  // Size styles
  const sizeStyles = {
    small: "px-3 py-1.5 text-sm",
    medium: "px-4 py-2 text-base",
    large: "px-6 py-3 text-lg"
  };

  const handleClick = () => {
    if (!disabled && !loading && onClick) {
      onClick();
    }
  };

  return (
    <button
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      disabled={disabled || loading}
      className={`
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        rounded-lg font-medium
        flex items-center gap-2 justify-center
        transition-all duration-200
        shadow-md hover:shadow-lg
        disabled:opacity-50 disabled:cursor-not-allowed
        ${className}
      `}
    >
      {loading ? (
        <>
          <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span>Thinking...</span>
        </>
      ) : (
        <>
          {icon}
          <span>{label}</span>
        </>
      )}
    </button>
  );
};

export default AgentButton;
