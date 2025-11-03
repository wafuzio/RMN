import { Skeleton } from "@/components/ui/skeleton";

export function SkeletonGrid({ count=8 }: { count?: number }) {
  return (
    <div className="columns-1 sm:columns-2 lg:columns-3 xl:columns-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div className="mb-4 break-inside-avoid" key={i}>
          <div className="card-surface overflow-hidden">
            <Skeleton className="h-[200px] w-full" />
            <div className="p-4 space-y-2">
              <Skeleton className="h-5 w-3/5" />
              <Skeleton className="h-4 w-2/5" />
              <Skeleton className="h-3 w-1/4" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
