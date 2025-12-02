import { AdGroup } from "@/lib/aggregateAds";
import { AdCard, Ad } from "./AdCard";
import { Badge } from "@/components/ui/badge";

export function AdCardGroup({
  group,
  onRemove,
  onOpen,
  draggableProps,
  dragIndex,
  dragOverIndex,
  currentIndex,
  priority,
  isLeftColumn = false
}: {
  group: AdGroup;
  onRemove: (groupId: string) => void;
  onOpen: (group: AdGroup) => void;
  draggableProps?: any;
  dragIndex?: number | null;
  dragOverIndex?: number | null;
  currentIndex?: number;
  priority?: boolean;
  isLeftColumn?: boolean;
}) {
  // Convert cover to Ad type for existing AdCard component
  // Use first keyword or join multiple keywords
  const keywordDisplay = group.keywords.length > 0 ? group.keywords.join(', ') : group.cover.keyword;
  
  // Create custom timestamp display for grouped ads with styled badge
  const timestampDisplay = group.count > 1 
    ? `BADGE_START${group.count}BADGE_END — ${new Date(group.first_seen).toLocaleDateString()} → ${new Date(group.last_seen).toLocaleDateString()}`
    : group.last_seen;
  
  const ad: Ad = {
    id: group.group_id,
    retailer: group.cover.retailer,
    client: group.cover.client,
    keyword: keywordDisplay,
    ad_type: group.cover.ad_type,
    brand: group.cover.brand || '',
    message: group.cover.message || '',
    image_url: group.cover.image_url || '',
    video_url: group.cover.video_url,
    poster_url: group.cover.poster_url,
    timestamp: timestampDisplay,
    card_format: group.cover.card_format,
    dimensions: group.cover.dimensions,
  };

  return (
    <AdCard
      ad={ad}
      onRemove={() => onRemove(group.group_id)}
      onOpen={() => onOpen(group)}
      draggableProps={draggableProps}
      dragIndex={dragIndex}
      dragOverIndex={dragOverIndex}
      currentIndex={currentIndex}
      priority={priority}
      isLeftColumn={isLeftColumn}
    />
  );
}
