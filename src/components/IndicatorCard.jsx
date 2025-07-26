import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { TrendingUp, TrendingDown, Minus, Info } from 'lucide-react';

const IndicatorCard = ({ 
  title, 
  value, 
  unit = "", 
  description = "", 
  source = "", 
  variation = null, 
  variationPeriod = "",
  status = "updated",
  showInfo = false,
  onInfoClick = null
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

  const getSourceColor = () => {
    switch (source.toLowerCase()) {
      case 'bcra': return 'bg-blue-100 text-blue-800';
      case 'indec': return 'bg-red-100 text-red-800';
      case 'oficial': return 'bg-green-100 text-green-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <Card className="hover:shadow-lg transition-shadow duration-200">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
          {showInfo && onInfoClick && (
            <button 
              onClick={onInfoClick}
              className="p-1 hover:bg-muted rounded-full transition-colors"
            >
              <Info className="w-3 h-3 text-muted-foreground" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {source && (
            <Badge className={getSourceColor()}>{source}</Badge>
          )}
          <Badge variant={getBadgeVariant()}>
            {status === 'loading' ? 'Cargando...' : 'Actualizado'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between mb-2">
          <div className="text-2xl font-bold">
            {value}{unit}
          </div>
          {variation && (
            <div className={`flex items-center gap-1 ${getVariationColor()}`}>
              {getVariationIcon()}
              <span className="text-sm font-medium">
                {variation > 0 ? '+' : ''}{variation}%
              </span>
            </div>
          )}
        </div>
        {description && (
          <p className="text-xs text-muted-foreground">
            {description}
          </p>
        )}
        {variation && variationPeriod && (
          <p className="text-xs text-muted-foreground mt-1">
            {variationPeriod}
          </p>
        )}
      </CardContent>
    </Card>
  );
};

export default IndicatorCard;

