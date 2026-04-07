/**
 * Tests for API configuration utilities.
 */

import { validateApiResponse, extractSafeErrorMessage, buildApiUrl, API_ENDPOINTS } from './api';

describe('API_ENDPOINTS', () => {
  it('has all expected endpoint keys', () => {
    expect(API_ENDPOINTS.ROSA_CLUSTERS).toBe('/api/rosa/clusters');
    expect(API_ENDPOINTS.ANSIBLE_RUN_TASK).toBe('/api/ansible/run-task');
    expect(API_ENDPOINTS.ANSIBLE_RUN_PLAYBOOK).toBe('/api/ansible/run-playbook');
    expect(API_ENDPOINTS.JOBS_HISTORY).toBe('/api/jobs');
    expect(API_ENDPOINTS.VERSIONS).toBe('/api/versions');
    expect(API_ENDPOINTS.CAPI_COMPONENT_VERSIONS).toBe('/api/capi/component-versions');
  });
});

describe('buildApiUrl', () => {
  it('builds full URL from endpoint', () => {
    const url = buildApiUrl('/api/rosa/clusters');
    expect(url).toContain('/api/rosa/clusters');
  });

  it('works with API_ENDPOINTS constants', () => {
    const url = buildApiUrl(API_ENDPOINTS.JOBS_HISTORY);
    expect(url).toContain('/api/jobs');
  });
});

describe('validateApiResponse', () => {
  it('returns response when valid object with no required fields', () => {
    const response = { data: 'test' };
    expect(validateApiResponse(response)).toBe(response);
  });

  it('returns response when all required fields present', () => {
    const response = { name: 'test', status: 'ok' };
    expect(validateApiResponse(response, ['name', 'status'])).toBe(response);
  });

  it('throws on null response', () => {
    expect(() => validateApiResponse(null)).toThrow('Invalid API response format');
  });

  it('throws on undefined response', () => {
    expect(() => validateApiResponse(undefined)).toThrow('Invalid API response format');
  });

  it('throws on non-object response', () => {
    expect(() => validateApiResponse('string')).toThrow('Invalid API response format');
  });

  it('throws when required field is missing', () => {
    expect(() => validateApiResponse({ name: 'test' }, ['name', 'status'])).toThrow(
      'Missing required field: status'
    );
  });

  it('accepts empty expectedFields array', () => {
    const response = { anything: true };
    expect(validateApiResponse(response, [])).toBe(response);
  });
});

describe('extractSafeErrorMessage', () => {
  const originalEnv = process.env.NODE_ENV;

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
  });

  it('returns full error message in development', () => {
    process.env.NODE_ENV = 'development';
    const error = new Error('Detailed error info');
    expect(extractSafeErrorMessage(error)).toBe('Detailed error info');
  });

  it('returns default message for error without message in development', () => {
    process.env.NODE_ENV = 'development';
    expect(extractSafeErrorMessage({})).toBe('An error occurred');
  });

  it('sanitizes fetch errors in production', () => {
    process.env.NODE_ENV = 'production';
    const error = new Error('Failed to fetch data');
    expect(extractSafeErrorMessage(error)).toBe('Network connection failed');
  });

  it('sanitizes JSON errors in production', () => {
    process.env.NODE_ENV = 'production';
    const error = new Error('Unexpected token in JSON');
    expect(extractSafeErrorMessage(error)).toBe('Invalid server response');
  });

  it('returns generic message for unknown errors in production', () => {
    process.env.NODE_ENV = 'production';
    const error = new Error('Something weird happened');
    expect(extractSafeErrorMessage(error)).toBe('An error occurred. Please try again.');
  });

  it('returns generic message for error without message in production', () => {
    process.env.NODE_ENV = 'production';
    expect(extractSafeErrorMessage({})).toBe('An error occurred. Please try again.');
  });
});
