export type DrawingTool = 'trendline' | 'horizontal' | 'fibonacci' | 'channel' | 'rectangle' | 'crosshair' | 'none';

export interface DrawingPoint {
  time: number;  // UTC timestamp
  price: number;
}

export interface Drawing {
  id: string;
  tool: DrawingTool;
  points: DrawingPoint[];
  color: string;
  lineWidth: number;
  symbol: string;  // which pair this drawing belongs to
}

// Fibonacci levels
export const FIBONACCI_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];

// Available colors for drawings
export const DRAWING_COLORS = [
  '#3b82f6', // blue
  '#10b981', // green
  '#ef4444', // red
  '#f59e0b', // yellow
  '#8b5cf6', // purple
  '#ec4899', // pink
];

// Generate unique ID
export function generateDrawingId(): string {
  return `drawing_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// Get localStorage key for a symbol
function getStorageKey(symbol: string): string {
  return `trading_drawings_${symbol}`;
}

// Save drawings to localStorage per symbol
export function saveDrawings(symbol: string, drawings: Drawing[]): void {
  try {
    localStorage.setItem(getStorageKey(symbol), JSON.stringify(drawings));
  } catch (e) {
    console.error('Failed to save drawings:', e);
  }
}

// Load drawings from localStorage per symbol
export function loadDrawings(symbol: string): Drawing[] {
  try {
    const stored = localStorage.getItem(getStorageKey(symbol));
    if (stored) {
      return JSON.parse(stored);
    }
  } catch (e) {
    console.error('Failed to load drawings:', e);
  }
  return [];
}

// Delete a specific drawing
export function deleteDrawing(symbol: string, drawingId: string): void {
  const drawings = loadDrawings(symbol);
  const filtered = drawings.filter(d => d.id !== drawingId);
  saveDrawings(symbol, filtered);
}

// Clear all drawings for a symbol
export function clearDrawings(symbol: string): void {
  try {
    localStorage.removeItem(getStorageKey(symbol));
  } catch (e) {
    console.error('Failed to clear drawings:', e);
  }
}

// Add a new drawing
export function addDrawing(symbol: string, drawing: Drawing): void {
  const drawings = loadDrawings(symbol);
  drawings.push(drawing);
  saveDrawings(symbol, drawings);
}

// Remove the last drawing (for undo)
export function undoLastDrawing(symbol: string): Drawing | null {
  const drawings = loadDrawings(symbol);
  if (drawings.length === 0) return null;
  const removed = drawings.pop()!;
  saveDrawings(symbol, drawings);
  return removed;
}
