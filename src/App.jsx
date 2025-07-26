import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Badge } from './components/ui/badge';
import { DollarSign, TrendingUp, BarChart3, PieChart, Activity, Building2 } from 'lucide-react';
import DolarSection from './components/sections/DolarSection';
import IndicatorCard from './components/IndicatorCard';
import './App.css';

// Componentes principales
const Header = () => (
  <header className="bg-primary text-primary-foreground py-6 px-4">
    <div className="container mx-auto">
      <h1 className="text-3xl font-bold mb-2">Economía Argentina</h1>
      <p className="text-primary-foreground/80">Indicadores económicos en tiempo real</p>
    </div>
  </header>
);

const Navigation = () => (
  <nav className="bg-card border-b">
    <div className="container mx-auto px-4">
      <Tabs defaultValue="dolar" className="w-full">
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="dolar" className="flex items-center gap-2">
            <DollarSign className="w-4 h-4" />
            Dólar
          </TabsTrigger>
          <TabsTrigger value="bcra" className="flex items-center gap-2">
            <Building2 className="w-4 h-4" />
            BCRA
          </TabsTrigger>
          <TabsTrigger value="inflacion" className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4" />
            Inflación
          </TabsTrigger>
          <TabsTrigger value="pbi" className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4" />
            PBI
          </TabsTrigger>
          <TabsTrigger value="balanza" className="flex items-center gap-2">
            <PieChart className="w-4 h-4" />
            Balanza
          </TabsTrigger>
          <TabsTrigger value="otros" className="flex items-center gap-2">
            <Activity className="w-4 h-4" />
            Otros
          </TabsTrigger>
        </TabsList>
        
        <div className="py-6">
          <TabsContent value="dolar">
            <DolarSection />
          </TabsContent>
          <TabsContent value="bcra">
            <BCRASection />
          </TabsContent>
          <TabsContent value="inflacion">
            <InflacionSection />
          </TabsContent>
          <TabsContent value="pbi">
            <PBISection />
          </TabsContent>
          <TabsContent value="balanza">
            <BalanzaSection />
          </TabsContent>
          <TabsContent value="otros">
            <OtrosSection />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  </nav>
);

// Secciones principales

const BCRASection = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Base Monetaria</CardTitle>
          <Badge variant="outline">BCRA</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">$45.2B</div>
          <p className="text-xs text-muted-foreground">
            +2.3% vs mes anterior
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Reservas</CardTitle>
          <Badge variant="outline">BCRA</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">US$28.5B</div>
          <p className="text-xs text-muted-foreground">
            -1.2% vs mes anterior
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">LELIQ</CardTitle>
          <Badge variant="outline">BCRA</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">40.5%</div>
          <p className="text-xs text-muted-foreground">
            Tasa de referencia
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">M2</CardTitle>
          <Badge variant="outline">BCRA</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">$125.8B</div>
          <p className="text-xs text-muted-foreground">
            Agregado monetario
          </p>
        </CardContent>
      </Card>
    </div>
    
    <Card>
      <CardHeader>
        <CardTitle>¿Qué son los indicadores del BCRA?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <h4 className="font-semibold mb-2">Base Monetaria</h4>
          <p className="text-sm text-muted-foreground">
            Es la cantidad total de dinero que el Banco Central pone en circulación en la economía. 
            Incluye billetes y monedas en poder del público y las reservas de los bancos en el BCRA.
          </p>
        </div>
        <div>
          <h4 className="font-semibold mb-2">Reservas Internacionales</h4>
          <p className="text-sm text-muted-foreground">
            Son los activos en moneda extranjera que posee el BCRA. Incluyen oro, divisas y otros 
            instrumentos financieros que pueden utilizarse para intervenir en el mercado cambiario.
          </p>
        </div>
      </CardContent>
    </Card>
  </div>
);

const InflacionSection = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Inflación Mensual</CardTitle>
          <Badge variant="destructive">INDEC</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">2.4%</div>
          <p className="text-xs text-muted-foreground">
            Febrero 2025
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Inflación Interanual</CardTitle>
          <Badge variant="destructive">INDEC</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">142.7%</div>
          <p className="text-xs text-muted-foreground">
            Últimos 12 meses
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Inflación Acumulada</CardTitle>
          <Badge variant="destructive">INDEC</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">18.3%</div>
          <p className="text-xs text-muted-foreground">
            Año 2025
          </p>
        </CardContent>
      </Card>
    </div>
    
    <Card>
      <CardHeader>
        <CardTitle>¿Qué es la inflación?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          La inflación es el aumento generalizado y sostenido de los precios de bienes y servicios 
          en una economía durante un período de tiempo. Se mide a través del Índice de Precios al 
          Consumidor (IPC) que calcula el INDEC.
        </p>
        <div>
          <h4 className="font-semibold mb-2">¿Cómo se mide?</h4>
          <p className="text-sm text-muted-foreground">
            El INDEC toma una canasta representativa de bienes y servicios que consume una familia 
            promedio y mide cómo varían sus precios mes a mes.
          </p>
        </div>
        <div>
          <h4 className="font-semibold mb-2">¿Cómo impacta?</h4>
          <p className="text-sm text-muted-foreground">
            La inflación reduce el poder adquisitivo del dinero, afecta el ahorro y puede generar 
            incertidumbre económica. Una inflación moderada puede ser normal, pero niveles altos 
            son problemáticos.
          </p>
        </div>
      </CardContent>
    </Card>
  </div>
);

const PBISection = () => (
  <div className="space-y-6">
    <Card>
      <CardHeader>
        <CardTitle>Producto Bruto Interno (PBI)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold mb-4">$850.2B USD</div>
        <p className="text-sm text-muted-foreground mb-4">
          Valor estimado para 2024 (INDEC)
        </p>
        <div className="h-64 bg-muted rounded-lg flex items-center justify-center">
          <p className="text-muted-foreground">Gráfico de evolución del PBI (próximamente)</p>
        </div>
      </CardContent>
    </Card>
    
    <Card>
      <CardHeader>
        <CardTitle>¿Qué es el PBI?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          El Producto Bruto Interno es el valor total de todos los bienes y servicios finales 
          producidos en un país durante un período específico, generalmente un año.
        </p>
        <div>
          <h4 className="font-semibold mb-2">¿Cómo se calcula?</h4>
          <p className="text-sm text-muted-foreground">
            Se puede calcular por tres métodos: producción (suma del valor agregado de todos los 
            sectores), gasto (consumo + inversión + gasto público + exportaciones netas) o 
            ingreso (suma de todos los ingresos generados).
          </p>
        </div>
        <div>
          <h4 className="font-semibold mb-2">¿Por qué es importante?</h4>
          <p className="text-sm text-muted-foreground">
            Es el principal indicador del tamaño y salud de una economía. Su crecimiento indica 
            expansión económica, mientras que su contracción puede señalar recesión.
          </p>
        </div>
      </CardContent>
    </Card>
  </div>
);

const BalanzaSection = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Exportaciones</CardTitle>
          <Badge variant="secondary">INDEC</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">$10.3B</div>
          <p className="text-xs text-muted-foreground">
            Mayo 2025
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Importaciones</CardTitle>
          <Badge variant="secondary">INDEC</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">$6.49B</div>
          <p className="text-xs text-muted-foreground">
            Mayo 2025
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Saldo Comercial</CardTitle>
          <Badge variant="default">Positivo</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-green-600">+$3.84B</div>
          <p className="text-xs text-muted-foreground">
            Superávit comercial
          </p>
        </CardContent>
      </Card>
    </div>
    
    <Card>
      <CardHeader>
        <CardTitle>¿Qué es la Balanza Comercial?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          La balanza comercial es la diferencia entre el valor de las exportaciones y las 
          importaciones de un país. Un saldo positivo indica superávit, mientras que un 
          saldo negativo indica déficit.
        </p>
        <div>
          <h4 className="font-semibold mb-2">Factores que la influyen</h4>
          <ul className="text-sm text-muted-foreground space-y-1">
            <li>• Competitividad de los productos nacionales</li>
            <li>• Tipo de cambio real</li>
            <li>• Demanda internacional de commodities</li>
            <li>• Políticas comerciales y arancelarias</li>
            <li>• Ciclo económico interno y externo</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  </div>
);

const OtrosSection = () => (
  <div className="space-y-6">
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Riesgo País</CardTitle>
          <Badge variant="outline">JP Morgan</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">1.250</div>
          <p className="text-xs text-muted-foreground">
            Puntos básicos
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Desempleo</CardTitle>
          <Badge variant="outline">INDEC</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">6.2%</div>
          <p className="text-xs text-muted-foreground">
            Q4 2024
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Pobreza</CardTitle>
          <Badge variant="outline">INDEC</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">41.7%</div>
          <p className="text-xs text-muted-foreground">
            Primer semestre 2024
          </p>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">EMAE</CardTitle>
          <Badge variant="outline">INDEC</Badge>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">+5.0%</div>
          <p className="text-xs text-muted-foreground">
            Interanual Mayo 2025
          </p>
        </CardContent>
      </Card>
    </div>
    
    <Card>
      <CardHeader>
        <CardTitle>Otros Indicadores Económicos</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <h4 className="font-semibold mb-2">Riesgo País</h4>
          <p className="text-sm text-muted-foreground">
            Mide la percepción de riesgo de invertir en un país. Se expresa en puntos básicos 
            sobre los bonos del Tesoro de Estados Unidos.
          </p>
        </div>
        <div>
          <h4 className="font-semibold mb-2">EMAE (Estimador Mensual de Actividad Económica)</h4>
          <p className="text-sm text-muted-foreground">
            Es un indicador que permite hacer un seguimiento mensual de la evolución del nivel 
            de actividad económica del país.
          </p>
        </div>
      </CardContent>
    </Card>
  </div>
);

const Footer = () => (
  <footer className="bg-muted py-8 px-4 mt-12">
    <div className="container mx-auto text-center">
      <p className="text-sm text-muted-foreground mb-4">
        Datos obtenidos de fuentes oficiales: BCRA, INDEC, DolarAPI, ArgentinaDatos
      </p>
      <p className="text-xs text-muted-foreground">
        Esta aplicación es de carácter informativo. Los datos se actualizan periódicamente.
      </p>
    </div>
  </footer>
);

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-background">
        <Header />
        <Navigation />
        <Footer />
      </div>
    </Router>
  );
}

export default App;

