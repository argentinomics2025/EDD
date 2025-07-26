import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

const DolarCard = ({ 
  title, 
  value, 
  compra, 
  venta, 
  variation = null, 
  lastUpdate = "Actualizado",
  status = "updated" 
}) => {
  const getVariationIcon = () => {
    if (!variation) return null;
    if (variation > 0) return <TrendingUp className="w-4 h-4 text-green-600" />;
    if (variation < 0) return <TrendingDown className="w-4 h-4 text-red-600" />;
    return <Minus className="w-4 h-4 text-gray-500" />;
  };

  const getVariationColor = () => {
    if (!variation) return "text-muted-foreground";
    if (variation > 0) return "text-green-600";
    if (variation < 0) return "text-red-600";
    return "text-muted-foreground";
  };

  const getBadgeVariant = () => {
    switch (status) {
      case 'updated': return 'secondary';
      case 'loading': return 'outline';
      case 'error': return 'destructive';
      default: return 'secondary';
    }
  };

  return (
    <Card className="hover:shadow-lg transition-shadow duration-200">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Badge variant={getBadgeVariant()}>{lastUpdate}</Badge>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between mb-2">
          <div className="text-2xl font-bold">${value}</div>
          {variation && (
            <div className={`flex items-center gap-1 ${getVariationColor()}`}>
              {getVariationIcon()}
              <span className="text-sm font-medium">
                {variation > 0 ? '+' : ''}{variation}%
              </span>
            </div>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Compra: ${compra} | Venta: ${venta}
        </p>
      </CardContent>
    </Card>
  );
};

export default DolarCard;

