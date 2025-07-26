import { useState, useEffect, useCallback } from 'react';

const useApi = (apiFunction, dependencies = []) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await apiFunction();
      setData(result);
    } catch (err) {
      setError(err.message || 'Error al cargar los datos');
      console.error('API Error:', err);
    } finally {
      setLoading(false);
    }
  }, [apiFunction]);

  useEffect(() => {
    fetchData();
  }, [fetchData, ...dependencies]);

  const retry = useCallback(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, retry };
};

export default useApi;

