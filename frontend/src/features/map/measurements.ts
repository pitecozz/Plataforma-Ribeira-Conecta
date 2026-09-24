export type Coordinate = [number, number];
const radius = 6371008.8;
const radians = (value: number) => value * Math.PI / 180;
export function distanceMetres(points: Coordinate[]): number {
  return points.slice(1).reduce((total, point, index) => {
    const [aLon, aLat] = points[index]; const [bLon, bLat] = point;
    const dLat = radians(bLat - aLat); const dLon = radians(bLon - aLon);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(radians(aLat)) * Math.cos(radians(bLat)) * Math.sin(dLon / 2) ** 2;
    return total + 2 * radius * Math.asin(Math.sqrt(h));
  }, 0);
}
export function areaSquareMetres(points: Coordinate[]): number {
  if (points.length < 3) return 0;
  const lat = points.reduce((sum, point) => sum + point[1], 0) / points.length;
  const scaleX = 111320 * Math.cos(radians(lat)); const scaleY = 110540;
  return Math.abs(points.reduce((sum, point, index) => { const next = points[(index + 1) % points.length]; return sum + (point[0] * scaleX * next[1] * scaleY - next[0] * scaleX * point[1] * scaleY); }, 0) / 2);
}
