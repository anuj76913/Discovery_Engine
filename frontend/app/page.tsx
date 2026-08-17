import { loadOpportunityAreas } from "@/lib/data";
import Dashboard from "@/components/Dashboard";
import EmptyState from "@/components/EmptyState";

export default async function Page() {
  const data = await loadOpportunityAreas();

  if (!data) {
    return (
      <div className="mx-auto flex min-h-screen max-w-5xl items-center px-4 py-8 sm:px-8">
        <EmptyState />
      </div>
    );
  }

  return <Dashboard data={data} />;
}
