import React, { useState, useEffect } from 'react';
import { ArrowPathIcon, ChartBarIcon } from '@heroicons/react/24/outline';
import { buildApiUrl } from '../../config/api';

const JenkinsTestResultsTrend = () => {
  const [trendData, setTrendData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchTrendData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(buildApiUrl('/api/jenkins/test-results-trend'));
      const data = await response.json();

      console.log('Jenkins trend data:', data);

      if (data.success && Array.isArray(data.trend)) {
        // Reverse to show oldest to newest (left to right)
        const reversed = data.trend.reverse();
        console.log('Setting trend data with', reversed.length, 'builds');
        setTrendData(reversed);
      } else {
        throw new Error(data.message || 'Failed to fetch Jenkins test results');
      }
    } catch (err) {
      console.error('Error fetching Jenkins trend:', err);
      setError(err.message || 'Failed to load test results');
    } finally {
      setLoading(false);
    }
  };

  // Calculate max count for scaling with better padding
  const maxCount = Math.max(...trendData.map(d => d.totalCount), 1);
  const yAxisMax = Math.ceil(maxCount * 1.1 / 10) * 10; // Round up to nearest 10 with 10% padding

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      {/* Header - Simple styling to match page */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">Jenkins Test Results</h3>
          <button
            onClick={fetchTrendData}
            disabled={loading}
            className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium flex items-center gap-2 border border-blue-200"
          >
            <ArrowPathIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {error ? (
          <div className="text-center py-12 bg-red-50 border-2 border-red-200 rounded-lg">
            <div className="text-red-600 font-semibold mb-2">Failed to load test results</div>
            <p className="text-sm text-red-500">{error}</p>
          </div>
        ) : loading ? (
          <div className="text-center py-12">
            <ArrowPathIcon className="h-10 w-10 animate-spin mx-auto mb-3 text-blue-500" />
            <p className="text-sm font-medium text-gray-600">Loading test results...</p>
          </div>
        ) : trendData.length === 0 ? (
          <div className="text-center py-12 bg-gray-100 border-2 border-gray-300 rounded-lg">
            <p className="text-sm font-medium text-gray-600 mb-3">Click Refresh to load test results</p>
            <button
              onClick={fetchTrendData}
              className="px-4 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded text-sm transition-colors font-medium border border-blue-200"
            >
              Load Data
            </button>
          </div>
        ) : (
          <div>
            {/* Chart - Compact design */}
            <div className="relative mb-4 bg-white p-4 rounded border border-gray-200" style={{ height: '240px' }}>
              {/* Y-axis labels */}
              <div className="absolute left-0 top-0 bottom-0 flex flex-col justify-between text-xs font-bold text-gray-700 pr-4 pt-8 pb-24" style={{ width: '50px' }}>
                <span className="text-right">{yAxisMax}</span>
                <span className="text-right">{Math.floor(yAxisMax * 0.75)}</span>
                <span className="text-right">{Math.floor(yAxisMax * 0.5)}</span>
                <span className="text-right">{Math.floor(yAxisMax * 0.25)}</span>
                <span className="text-right">0</span>
              </div>

              {/* Chart area */}
              <div className="absolute" style={{ left: '56px', right: '24px', top: '32px', bottom: '80px' }}>
                <div className="relative h-full border-l-2 border-b-2 border-gray-500">
                  {/* Horizontal grid lines */}
                  <div className="absolute inset-0">
                    {[0, 25, 50, 75, 100].map(pct => (
                      <div
                        key={pct}
                        className="absolute w-full border-t"
                        style={{
                          bottom: `${pct}%`,
                          borderColor: pct === 0 ? '#6b7280' : '#e5e7eb',
                          borderWidth: pct === 0 ? '2px' : '1px',
                          borderStyle: pct === 0 ? 'solid' : 'dashed'
                        }}
                      ></div>
                    ))}
                  </div>

                  {/* Stacked Bar Chart with enhanced styling */}
                  <div className="absolute inset-0 flex items-end justify-between" style={{ padding: '0 8px', gap: '6px' }}>
                    {trendData.map((build, index) => (
                      <div
                        key={build.build}
                        className="flex-1 group relative flex flex-col justify-end cursor-pointer transition-all duration-200"
                        style={{ height: '100%' }}
                        onClick={() => window.open(`https://jenkins-csb-rhacm-tests.dno.corp.redhat.com/job/CI-Jobs/job/capi_tests/${build.build}/`, '_blank')}
                      >
                        {/* Pass (top) - with enhanced styling */}
                        {build.passCount > 0 && (
                          <div
                            className="group-hover:brightness-110 transition-all duration-200 border-r border-l border-white/30"
                            style={{
                              height: `${(build.passCount / yAxisMax) * 100}%`,
                              backgroundColor: '#1e88e5',
                              width: '100%',
                              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                              borderTopLeftRadius: '4px',
                              borderTopRightRadius: '4px'
                            }}
                          ></div>
                        )}

                        {/* Skip (middle) - with enhanced styling */}
                        {build.skipCount > 0 && (
                          <div
                            className="group-hover:brightness-110 transition-all duration-200 border-r border-l border-white/30"
                            style={{
                              height: `${(build.skipCount / yAxisMax) * 100}%`,
                              backgroundColor: '#ffc107',
                              width: '100%',
                              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                              borderTopLeftRadius: build.passCount === 0 ? '4px' : '0',
                              borderTopRightRadius: build.passCount === 0 ? '4px' : '0'
                            }}
                          ></div>
                        )}

                        {/* Fail (bottom) - with enhanced styling */}
                        {build.failCount > 0 && (
                          <div
                            className="group-hover:brightness-110 transition-all duration-200 border-r border-l border-white/30"
                            style={{
                              height: `${(build.failCount / yAxisMax) * 100}%`,
                              backgroundColor: '#d32f2f',
                              width: '100%',
                              boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                              borderTopLeftRadius: (build.passCount === 0 && build.skipCount === 0) ? '4px' : '0',
                              borderTopRightRadius: (build.passCount === 0 && build.skipCount === 0) ? '4px' : '0'
                            }}
                          ></div>
                        )}

                        {/* Hover effect overlay */}
                        <div className="absolute inset-0 bg-white/0 group-hover:bg-white/10 transition-all duration-200 pointer-events-none rounded-t"></div>

                        {/* Enhanced Tooltip */}
                        <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-4 opacity-0 group-hover:opacity-100 transition-all duration-200 z-30 pointer-events-none group-hover:translate-y-[-4px]">
                          <div className="bg-gradient-to-br from-gray-900 to-gray-800 text-white text-xs rounded-xl px-5 py-4 shadow-2xl whitespace-nowrap border-2 border-gray-700">
                            <div className="font-bold mb-2.5 text-blue-300 border-b border-gray-600 pb-2 text-sm">Build #{build.build}</div>
                            <div className="space-y-2">
                              <div className="flex items-center gap-3">
                                <div className="w-3.5 h-3.5 rounded shadow-sm" style={{ backgroundColor: '#1e88e5' }}></div>
                                <span className="text-gray-300">Pass:</span>
                                <span className="font-bold text-white ml-auto">{build.passCount}</span>
                              </div>
                              <div className="flex items-center gap-3">
                                <div className="w-3.5 h-3.5 rounded shadow-sm" style={{ backgroundColor: '#d32f2f' }}></div>
                                <span className="text-gray-300">Fail:</span>
                                <span className="font-bold text-white ml-auto">{build.failCount}</span>
                              </div>
                              {build.skipCount > 0 && (
                                <div className="flex items-center gap-3">
                                  <div className="w-3.5 h-3.5 rounded shadow-sm" style={{ backgroundColor: '#ffc107' }}></div>
                                  <span className="text-gray-300">Skip:</span>
                                  <span className="font-bold text-white ml-auto">{build.skipCount}</span>
                                </div>
                              )}
                            </div>
                            <div className="border-t border-gray-600 mt-3 pt-3 flex items-center justify-between gap-4">
                              <span className="text-gray-400 text-xs font-medium">Pass Rate:</span>
                              <span className="font-bold text-green-400 text-sm">{build.passRate}%</span>
                            </div>
                            {/* Tooltip arrow */}
                            <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-px">
                              <div className="border-[6px] border-transparent border-t-gray-900"></div>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* X-axis labels with better spacing */}
                <div className="absolute left-0 right-0 flex px-3" style={{ top: '100%', marginTop: '20px', gap: '8px' }}>
                  {trendData.map((build) => (
                    <div key={build.build} className="flex-1 text-center py-2">
                      <div className="text-xs text-gray-800 font-bold mb-2">#{build.build}</div>
                      <div className={`text-base font-bold inline-flex items-center justify-center w-6 h-6 rounded-full ${
                        build.result === 'SUCCESS' ? 'text-green-600 bg-green-50' :
                        build.result === 'FAILURE' ? 'text-red-600 bg-red-50' :
                        'text-yellow-600 bg-yellow-50'
                      }`}>
                        {build.result === 'SUCCESS' ? '✓' : build.result === 'FAILURE' ? '✗' : '~'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Legend - Simple */}
            <div className="flex items-center justify-center gap-6 text-xs mb-3 pb-3 border-b border-gray-200">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded" style={{ backgroundColor: '#1e88e5' }}></div>
                <span className="text-gray-700">Passed</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded" style={{ backgroundColor: '#ffc107' }}></div>
                <span className="text-gray-700">Skipped</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded" style={{ backgroundColor: '#d32f2f' }}></div>
                <span className="text-gray-700">Failed</span>
              </div>
            </div>

            {/* Summary Stats - Compact */}
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="bg-blue-50 border border-blue-200 rounded p-3 text-center">
                <div className="text-2xl font-bold text-blue-700">
                  {trendData.length > 0 ? Math.round(trendData.reduce((sum, b) => sum + b.passRate, 0) / trendData.length) : 0}%
                </div>
                <div className="text-xs text-blue-900 uppercase">Avg Pass</div>
              </div>
              <div className="bg-green-50 border border-green-200 rounded p-3 text-center">
                <div className="text-2xl font-bold text-green-700">
                  {trendData.filter(b => b.result === 'SUCCESS').length}
                </div>
                <div className="text-xs text-green-900 uppercase">Success</div>
              </div>
              <div className="bg-purple-50 border border-purple-200 rounded p-3 text-center">
                <div className="text-2xl font-bold text-purple-700">
                  {trendData.reduce((sum, b) => sum + b.totalCount, 0)}
                </div>
                <div className="text-xs text-purple-900 uppercase">Total</div>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
};

export default JenkinsTestResultsTrend;
