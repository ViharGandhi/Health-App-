import { notFound } from 'next/navigation';
import StrainTrendDetail from '@/components/StrainTrendDetail';
import { strainMetrics } from '@/lib/strain';

export default async function StrainMetricPage({ params }: { params: Promise<{ metric: string }> }) {
  const { metric } = await params;
  if (!strainMetrics.some(item => item.slug === metric)) notFound();
  return <StrainTrendDetail key={metric} slug={metric} />;
}
