import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Badge } from './ui/badge';
import { ExternalLink } from 'lucide-react';

const InfoModal = ({ 
  isOpen, 
  onClose, 
  title, 
  description, 
  details = [], 
  sources = [],
  category = "" 
}) => {
  const getCategoryColor = () => {
    switch (category.toLowerCase()) {
      case 'dolar': return 'bg-green-100 text-green-800';
      case 'bcra': return 'bg-blue-100 text-blue-800';
      case 'inflacion': return 'bg-red-100 text-red-800';
      case 'pbi': return 'bg-purple-100 text-purple-800';
      case 'balanza': return 'bg-orange-100 text-orange-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-2">
            <DialogTitle className="text-xl">{title}</DialogTitle>
            {category && (
              <Badge className={getCategoryColor()}>{category}</Badge>
            )}
          </div>
          <DialogDescription className="text-base">
            {description}
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 mt-4">
          {details.map((detail, index) => (
            <div key={index}>
              <h4 className="font-semibold mb-2">{detail.subtitle}</h4>
              <p className="text-sm text-muted-foreground">{detail.content}</p>
            </div>
          ))}
          
          {sources.length > 0 && (
            <div className="border-t pt-4">
              <h4 className="font-semibold mb-2">Fuentes oficiales:</h4>
              <div className="space-y-2">
                {sources.map((source, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <ExternalLink className="w-4 h-4 text-muted-foreground" />
                    <a 
                      href={source.url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-sm text-primary hover:underline"
                    >
                      {source.name}
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default InfoModal;

