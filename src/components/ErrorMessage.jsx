import React from 'react';
import { Card, CardContent } from './ui/card';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from './ui/button';

const ErrorMessage = ({ 
  title = "Error al cargar datos", 
  message = "No se pudieron obtener los datos. Por favor, intenta nuevamente.", 
  onRetry = null,
  showRetry = true 
}) => {
  return (
    <Card className="border-destructive/20 bg-destructive/5">
      <CardContent className="flex flex-col items-center justify-center py-8 text-center">
        <AlertTriangle className="w-12 h-12 text-destructive mb-4" />
        <h3 className="text-lg font-semibold text-destructive mb-2">{title}</h3>
        <p className="text-sm text-muted-foreground mb-4 max-w-md">{message}</p>
        {showRetry && onRetry && (
          <Button 
            variant="outline" 
            size="sm" 
            onClick={onRetry}
            className="flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Reintentar
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default ErrorMessage;

