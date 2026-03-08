import React, { useState, useEffect } from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import { buildApiUrl } from '../../config/api';

const GitHubRepoActivity = () => {
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchRepoActivity = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(buildApiUrl('/api/github/repo-activity'));
      const data = await response.json();

      console.log('GitHub repo activity data:', data);

      if (data.success && Array.isArray(data.repos)) {
        setRepos(data.repos);
      } else {
        throw new Error(data.message || 'Failed to fetch GitHub repo activity');
      }
    } catch (err) {
      console.error('Error fetching GitHub repo activity:', err);
      setError(err.message || 'Failed to load repo activity');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">Recent GitHub Activity (Last 7 Days)</h3>
          <button
            onClick={fetchRepoActivity}
            disabled={loading}
            className="px-3 py-1.5 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium flex items-center gap-2"
          >
            <ArrowPathIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {error ? (
          <div className="text-center py-4 bg-red-50 border border-red-200 rounded">
            <p className="text-xs text-red-600">{error}</p>
          </div>
        ) : loading ? (
          <div className="text-center py-4">
            <ArrowPathIcon className="h-5 w-5 animate-spin mx-auto mb-1 text-gray-400" />
            <p className="text-xs text-gray-500">Loading...</p>
          </div>
        ) : repos.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-xs text-gray-500 mb-2">Click Refresh to load GitHub activity</p>
            <button
              onClick={fetchRepoActivity}
              className="px-3 py-1.5 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded text-xs transition-colors font-medium"
            >
              Load Data
            </button>
          </div>
        ) : (
          <div className="space-y-1">
            {repos.map((repo, idx) => (
              <div key={idx} className="flex items-center justify-between py-2 px-3 hover:bg-gray-50 rounded border border-gray-200">
                <a
                  href={`https://github.com/${repo.repo}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline"
                  title={repo.repo}
                >
                  {repo.name}
                </a>
                <div className="flex items-center gap-2">
                  {repo.error ? (
                    <span className="text-xs text-orange-600 italic">Rate limited</span>
                  ) : (
                    <>
                      <span className={`text-sm font-bold ${repo.merged_prs_7d > 0 ? 'text-green-600' : 'text-gray-400'}`}>
                        {repo.merged_prs_7d || 0}
                      </span>
                      <span className="text-xs text-gray-500">merged</span>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default GitHubRepoActivity;
