import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Button } from '../ui/button';
import DolarCard from '../DolarCard';
import LoadingSpinner from '../LoadingSpinner';
import ErrorMessage from '../ErrorMessage';
import InfoModal from '../InfoModal';
import useApi from '../../hooks/useApi';
import { dolarApi, argentinadatosApi } from '../../lib/api';
import { Info, Calendar, TrendingUp } from 'lucide-react';

const DolarSection = () => {
  const [selectedPeriod, setSelectedPeriod] = useState('7d');
  const [showInfoModal, setShowInfoModal] = useState(false);
  const [selectedDolarInfo, setSelectedDolarInfo] = useState(null);

  // Cargar datos de cotizaciones actuales
  const { data: dolarData, loading: dolarLoading, error: dolarError, retry: retryDolar } = useApi(
    () => dolarApi.getAll()
  );

  // Cargar datos históricos
  const { data: historicalData, loading: historicalLoading, error: historicalError } = useApi(
    () => argentinadatosApi.getHistorical()
  );

  const dolarTypes = [
    { key: 'oficial', name: 'Dólar Oficial', description: 'Cotización oficial del BCRA' },
    { key: 'blue', name: 'Dólar Blue', description: 'Mercado paralelo o informal' },
    { key: 'bolsa', name: 'Dólar MEP', description: 'Mercado Electrónico de Pagos' },
    { key: 'ccl', name: 'Dólar CCL', description: 'Contado con Liquidación' },
    { key: 'tarjeta', name: 'Dólar Tarjeta', description: 'Para compras con tarjeta' },
    { key: 'mayorista', name: 'Dólar Mayorista', description: 'Mercado mayorista' }
  ];

  const dolarInfo = {
    oficial: {
      title: "Dólar Oficial",
      description: "Es la cotización oficial establecida por el Banco Central de la República Argentina (BCRA).",
      details: [
        {
          subtitle: "¿Cómo se determina?",
          content: "El BCRA establece la cotización oficial basándose en diversos factores económicos y políticas monetarias."
        },
        {
          subtitle: "¿Dónde se puede comprar?",
          content: "En bancos y casas de cambio autorizadas, con límites mensuales establecidos por el BCRA."
        }
      ],
      sources: [
        { name: "BCRA - Banco Central", url: "https://www.bcra.gob.ar" }
      ],
      category: "Dólar"
    },
    blue: {
      title: "Dólar Blue",
      description: "Es la cotización del dólar en el mercado paralelo o informal, también conocido como 'mercado negro'.",
      details: [
        {
          subtitle: "¿Por qué existe?",
          content: "Surge debido a las restricciones para acceder al dólar oficial, creando un mercado alternativo."
        },
        {
          subtitle: "¿Cómo se forma el precio?",
          content: "Se determina por la oferta y demanda en el mercado informal, sin intervención oficial."
        }
      ],
      sources: [
        { name: "Ámbito Financiero", url: "https://www.ambito.com" }
      ],
      category: "Dólar"
    }
  };

  const handleInfoClick = (dolarType) => {
    setSelectedDolarInfo(dolarInfo[dolarType] || null);
    setShowInfoModal(true);
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('es-AR', {
      style: 'currency',
      currency: 'ARS',
      minimumFractionDigits: 2
    }).format(value);
  };

  const getDolarByType = (type) => {
    if (!dolarData) return null;
    return dolarData.find(d => d.casa.toLowerCase() === type.toLowerCase());
  };

  if (dolarLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <LoadingSpinner size="lg" className="mb-4" />
          <p className="text-muted-foreground">Cargando cotizaciones del dólar...</p>
        </div>
      </div>
    );
  }

  if (dolarError) {
    return (
      <ErrorMessage
        title="Error al cargar cotizaciones"
        message={dolarError}
        onRetry={retryDolar}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Header con información */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Cotizaciones del Dólar</h2>
          <p className="text-muted-foreground">Valores actualizados en tiempo real</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowInfoModal(true)}
          className="flex items-center gap-2"
        >
          <Info className="w-4 h-4" />
          Información
        </Button>
      </div>

      {/* Grid de cotizaciones */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {dolarTypes.map((type) => {
          const dolarInfo = getDolarByType(type.key);
          if (!dolarInfo) return null;

          return (
            <DolarCard
              key={type.key}
              title={type.name}
              value={formatCurrency((dolarInfo.compra + dolarInfo.venta) / 2)}
              compra={formatCurrency(dolarInfo.compra)}
              venta={formatCurrency(dolarInfo.venta)}
              lastUpdate="Actualizado"
              status="updated"
            />
          );
        })}
      </div>

      {/* Sección de gráfico histórico */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5" />
                Evolución Histórica
              </CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                Gráfico de cotizaciones en el tiempo
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Tabs value={selectedPeriod} onValueChange={setSelectedPeriod}>
                <TabsList>
                  <TabsTrigger value="7d">7D</TabsTrigger>
                  <TabsTrigger value="30d">30D</TabsTrigger>
                  <TabsTrigger value="90d">90D</TabsTrigger>
                  <TabsTrigger value="1y">1A</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {historicalLoading ? (
            <div className="h-64 flex items-center justify-center">
              <div className="text-center">
                <LoadingSpinner size="md" className="mb-2" />
                <p className="text-sm text-muted-foreground">Cargando datos históricos...</p>
              </div>
            </div>
          ) : historicalError ? (
            <div className="h-64 flex items-center justify-center">
              <p className="text-muted-foreground">
                Los gráficos históricos estarán disponibles próximamente
              </p>
            </div>
          ) : (
            <div className="h-64 bg-muted rounded-lg flex items-center justify-center">
              <div className="text-center">
                <Calendar className="w-12 h-12 text-muted-foreground mb-2 mx-auto" />
                <p className="text-muted-foreground">
                  Gráfico histórico (próximamente)
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  Período seleccionado: {selectedPeriod}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Información educativa */}
      <Card>
        <CardHeader>
          <CardTitle>¿Qué significan estas cotizaciones?</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {dolarTypes.slice(0, 4).map((type) => (
              <div key={type.key} className="p-4 border rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-semibold">{type.name}</h4>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleInfoClick(type.key)}
                    className="h-6 w-6 p-0"
                  >
                    <Info className="w-3 h-3" />
                  </Button>
                </div>
                <p className="text-sm text-muted-foreground">{type.description}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Modal de información */}
      <InfoModal
        isOpen={showInfoModal}
        onClose={() => setShowInfoModal(false)}
        title={selectedDolarInfo?.title || "Información sobre el Dólar"}
        description={selectedDolarInfo?.description || "Información general sobre las cotizaciones del dólar en Argentina."}
        details={selectedDolarInfo?.details || []}
        sources={selectedDolarInfo?.sources || []}
        category={selectedDolarInfo?.category || "Dólar"}
      />
    </div>
  );
};

export default DolarSection;

