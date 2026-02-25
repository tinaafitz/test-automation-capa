import React, { useEffect } from 'react';
import { CheckCircleIcon, XCircleIcon, InformationCircleIcon, ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useApp, useAppDispatch, AppActionTypes } from '../store/AppContext';

const ToastNotifications = () => {
  const { notifications } = useApp();
  const dispatch = useAppDispatch();

  const getIcon = (type) => {
    switch (type) {
      case 'success':
        return <CheckCircleIcon className="h-6 w-6 text-green-400" />;
      case 'error':
        return <XCircleIcon className="h-6 w-6 text-red-400" />;
      case 'warning':
        return <ExclamationTriangleIcon className="h-6 w-6 text-yellow-400" />;
      case 'info':
      default:
        return <InformationCircleIcon className="h-6 w-6 text-blue-400" />;
    }
  };

  const getBackgroundColor = (type) => {
    switch (type) {
      case 'success':
        return 'bg-green-50';
      case 'error':
        return 'bg-red-50';
      case 'warning':
        return 'bg-yellow-50';
      case 'info':
      default:
        return 'bg-blue-50';
    }
  };

  const getBorderColor = (type) => {
    switch (type) {
      case 'success':
        return 'border-green-200';
      case 'error':
        return 'border-red-200';
      case 'warning':
        return 'border-yellow-200';
      case 'info':
      default:
        return 'border-blue-200';
    }
  };

  const removeNotification = (id) => {
    dispatch({ type: AppActionTypes.REMOVE_NOTIFICATION, payload: id });
  };

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-md">
      {notifications.map((notification) => (
        <Toast
          key={notification.id}
          notification={notification}
          onRemove={removeNotification}
          getIcon={getIcon}
          getBackgroundColor={getBackgroundColor}
          getBorderColor={getBorderColor}
        />
      ))}
    </div>
  );
};

const Toast = ({ notification, onRemove, getIcon, getBackgroundColor, getBorderColor }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onRemove(notification.id);
    }, notification.duration || 5000);

    return () => clearTimeout(timer);
  }, [notification, onRemove]);

  return (
    <div
      className={`${getBackgroundColor(notification.type)} ${getBorderColor(notification.type)} border rounded-lg shadow-lg p-4 flex items-start gap-3 animate-slide-in-right`}
      style={{
        animation: 'slideInRight 0.3s ease-out',
      }}
    >
      <div className="flex-shrink-0">{getIcon(notification.type)}</div>
      <div className="flex-1 min-w-0">
        {notification.title && (
          <h3 className="text-sm font-semibold text-gray-900 mb-1">{notification.title}</h3>
        )}
        <p className="text-sm text-gray-700">{notification.message}</p>
      </div>
      <button
        onClick={() => onRemove(notification.id)}
        className="flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
      >
        <XMarkIcon className="h-5 w-5" />
      </button>
    </div>
  );
};

export default ToastNotifications;
