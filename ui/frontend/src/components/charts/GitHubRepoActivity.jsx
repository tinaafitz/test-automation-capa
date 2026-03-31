import React, { useState, useEffect } from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import { buildApiUrl } from '../../config/api';

const GitHubRepoActivity = () => {
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchRepoActivity = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(buildApiUrl('/api/github/repo-activity'));
      const data = await response.json();

      if (data.success && Array.isArray(data.repos)) {
        setRepos(data.repos);
        setLastUpdated(new Date());
      } else {
        throw new Error(data.message || 'Failed to fetch GitHub repo activity');
      }
    } catch (err) {
      setError(err.message || 'Failed to load repo activity');
    } finally {
      setLoading(false);
    }
  };

  // Auto-fetch on mount + poll every 5 minutes
  useEffect(() => {
    fetchRepoActivity();
    const interval = setInterval(fetchRepoActivity, 300000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">GitHub Activity</h3>
          <button
            onClick={fetchRepoActivity}
            disabled={loading}
            className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-md text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium flex items-center gap-2 border border-blue-200"
          >
            <ArrowPathIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
        {lastUpdated ? (
          <p className="text-xs text-gray-500 mt-0.5">Last 7 days &middot; Updated: {lastUpdated.toLocaleTimeString()}</p>
        ) : (
          <p className="text-xs text-gray-500 mt-0.5">Last 7 days</p>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {error ? (
          <div className="text-center py-6 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        ) : loading ? (
          <div className="text-center py-8 text-gray-500">
            <ArrowPathIcon className="h-6 w-6 animate-spin mx-auto mb-2" />
            <p className="text-sm">Loading...</p>
          </div>
        ) : repos.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-sm text-gray-500 mb-3">Click Refresh to load GitHub activity</p>
            <button
              onClick={fetchRepoActivity}
              className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-md text-xs transition-colors font-medium border border-blue-200"
            >
              Load Data
            </button>
          </div>
        ) : (
          <div className="space-y-2">
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
