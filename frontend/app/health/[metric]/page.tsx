import { notFound } from 'next/navigation';
import HealthTrendDetail from '@/components/HealthTrendDetail';
import { healthMetrics } from '@/lib/health';

export default async function HealthMetricPage({ params }: { params: Promise<{ metric: string }> }) {
  const { metric } = await params;
  if (!healthMetrics.some(item => item.slug === metric)) notFound();
  return <HealthTrendDetail slug={metric} />;
}
