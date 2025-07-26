// Configuración base para las APIs
const API_CONFIG = {
  dolarApi: {
    baseUrl: 'https://dolarapi.com/v1',
    timeout: 10000
  },
  argentinadatos: {
    baseUrl: 'https://api.argentinadatos.com/v1',
    timeout: 10000
  },
  bcra: {
    baseUrl: 'https://www.bcra.gob.ar/PublicacionesEstadisticas',
    timeout: 15000
  }
};

// Función helper para hacer requests HTTP
const fetchWithTimeout = async (url, options = {}) => {
  const { timeout = 10000, ...fetchOptions } = options;
  
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal
    });
    
    clearTimeout(id);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    clearTimeout(id);
    if (error.name === 'AbortError') {
      throw new Error('Request timeout');
    }
    throw error;
  }
};

// APIs del Dólar
export const dolarApi = {
  // Obtener todas las cotizaciones
  getAll: async () => {
    try {
      const response = await fetchWithTimeout(`${API_CONFIG.dolarApi.baseUrl}/dolares`);
      return response;
    } catch (error) {
      // Fallback con datos mock si la API falla
      console.warn('DolarAPI failed, using mock data:', error);
      return getMockDolarData();
    }
  },

  // Obtener cotización específica
  getSpecific: async (type) => {
    try {
      const response = await fetchWithTimeout(`${API_CONFIG.dolarApi.baseUrl}/dolares/${type}`);
      return response;
    } catch (error) {
      console.warn(`DolarAPI ${type} failed, using mock data:`, error);
      return getMockDolarData().find(d => d.casa.toLowerCase().includes(type.toLowerCase()));
    }
  }
};

// APIs de ArgentinaDatos
export const argentinadatosApi = {
  // Obtener cotizaciones históricas
  getHistorical: async (casa = '', fecha = '') => {
    try {
      let url = `${API_CONFIG.argentinadatos.baseUrl}/cotizaciones/dolares`;
      if (casa) url += `/${casa}`;
      if (fecha) url += `/${fecha}`;
      
      const response = await fetchWithTimeout(url);
      return response;
    } catch (error) {
      console.warn('ArgentinaDatos API failed:', error);
      return [];
    }
  }
};

// APIs del BCRA (usando datos mock por ahora)
export const bcraApi = {
  // Obtener principales variables
  getPrincipales: async () => {
    try {
      // Por ahora usamos datos mock ya que la API oficial requiere autenticación
      return getMockBCRAData();
    } catch (error) {
      console.warn('BCRA API failed:', error);
      return getMockBCRAData();
    }
  }
};

// APIs del INDEC (usando datos mock por ahora)
export const indecApi = {
  // Obtener datos de inflación
  getInflacion: async () => {
    try {
      // Por ahora usamos datos mock ya que no hay API pública directa
      return getMockInflacionData();
    } catch (error) {
      console.warn('INDEC API failed:', error);
      return getMockInflacionData();
    }
  },

  // Obtener datos del PBI
  getPBI: async () => {
    try {
      return getMockPBIData();
    } catch (error) {
      console.warn('PBI API failed:', error);
      return getMockPBIData();
    }
  },

  // Obtener datos de balanza comercial
  getBalanza: async () => {
    try {
      return getMockBalanzaData();
    } catch (error) {
      console.warn('Balanza API failed:', error);
      return getMockBalanzaData();
    }
  }
};

// Datos mock para desarrollo y fallback
const getMockDolarData = () => [
  {
    moneda: "USD",
    casa: "oficial",
    nombre: "Oficial",
    compra: 1240.00,
    venta: 1260.00,
    fechaActualizacion: new Date().toISOString()
  },
  {
    moneda: "USD",
    casa: "blue",
    nombre: "Blue",
    compra: 1300.00,
    venta: 1340.00,
    fechaActualizacion: new Date().toISOString()
  },
  {
    moneda: "USD",
    casa: "bolsa",
    nombre: "MEP",
    compra: 1265.00,
    venta: 1275.00,
    fechaActualizacion: new Date().toISOString()
  },
  {
    moneda: "USD",
    casa: "ccl",
    nombre: "CCL",
    compra: 1270.00,
    venta: 1280.00,
    fechaActualizacion: new Date().toISOString()
  },
  {
    moneda: "USD",
    casa: "tarjeta",
    nombre: "Tarjeta",
    compra: 1980.00,
    venta: 2020.00,
    fechaActualizacion: new Date().toISOString()
  },
  {
    moneda: "USD",
    casa: "mayorista",
    nombre: "Mayorista",
    compra: 1251.00,
    venta: 1260.00,
    fechaActualizacion: new Date().toISOString()
  }
];

const getMockBCRAData = () => ({
  baseMonetaria: {
    valor: 45200000000,
    variacion: 2.3,
    fecha: new Date().toISOString()
  },
  reservas: {
    valor: 28500000000,
    variacion: -1.2,
    fecha: new Date().toISOString()
  },
  leliq: {
    valor: 40.5,
    variacion: 0,
    fecha: new Date().toISOString()
  },
  m2: {
    valor: 125800000000,
    variacion: 1.8,
    fecha: new Date().toISOString()
  }
});

const getMockInflacionData = () => ({
  mensual: {
    valor: 2.4,
    periodo: "Febrero 2025",
    fecha: new Date().toISOString()
  },
  interanual: {
    valor: 142.7,
    periodo: "Últimos 12 meses",
    fecha: new Date().toISOString()
  },
  acumulada: {
    valor: 18.3,
    periodo: "Año 2025",
    fecha: new Date().toISOString()
  }
});

const getMockPBIData = () => ({
  valor: 850200000000,
  moneda: "USD",
  periodo: "2024",
  variacion: 3.5,
  fecha: new Date().toISOString()
});

const getMockBalanzaData = () => ({
  exportaciones: {
    valor: 10300000000,
    periodo: "Mayo 2025",
    variacion: 2.3
  },
  importaciones: {
    valor: 6490000000,
    periodo: "Mayo 2025",
    variacion: 37.3
  },
  saldo: {
    valor: 3840000000,
    tipo: "superavit"
  }
});

