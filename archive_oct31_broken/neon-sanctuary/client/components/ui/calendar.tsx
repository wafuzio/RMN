import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker } from "react-day-picker";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: CalendarProps) {
  React.useEffect(() => {
    // Add CSS rules for table alignment
    const styleId = "calendar-alignment-styles";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = `
        .rdp table {
          width: 100%;
          border-collapse: collapse;
        }
        .rdp tbody tr, .rdp thead tr {
          display: grid;
          grid-template-columns: repeat(7, 1fr);
        }
        .rdp thead th, .rdp tbody td {
          padding: 0;
          text-align: center;
        }
        .rdp thead th {
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 600;
          font-size: 12px;
          color: #4b5563;
        }
        .rdp tbody td {
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .rdp-day_selected:not([disabled]) {
          background-color: #3b82f6 !important;
          color: white !important;
          border-radius: 50% !important;
          font-weight: 600 !important;
        }
        .rdp-day_selected:not([disabled]):hover {
          background-color: #2563eb !important;
        }
      `;
      document.head.appendChild(style);
    }
  }, []);

  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn("p-3 rdp", className)}
      classNames={{
        months: "flex flex-col sm:flex-row gap-8",
        month: "space-y-4 relative",
        caption: "flex justify-center items-center py-2 relative",
        caption_label: "text-sm font-semibold",
        nav: "flex gap-2 absolute top-1 inset-x-0 justify-between px-1",
        nav_button: cn(
          buttonVariants({ variant: "outline" }),
          "h-7 w-7 bg-white p-0 opacity-60 hover:opacity-100 transition-opacity border border-gray-300",
        ),
        nav_button_previous: "",
        nav_button_next: "",
        table: "w-full",
        head_row: "",
        head_cell:
          "text-gray-600",
        row: "",
        cell: "[&:has([aria-selected].day-range-end)]:rounded-r-md [&:has([aria-selected].day-outside)]:bg-blue-100 [&:has([aria-selected])]:bg-blue-100 first:[&:has([aria-selected])]:rounded-l-md last:[&:has([aria-selected])]:rounded-r-md",
        day: cn(
          "h-9 w-9 p-0 font-normal transition-all hover:bg-gray-100",
        ),
        day_range_end: "day-range-end",
        day_selected:
          "bg-blue-500 text-white font-semibold rounded-full",
        day_today: "bg-white border-2 border-blue-500 text-blue-600 font-semibold rounded-full",
        day_outside:
          "day-outside text-gray-300 aria-selected:bg-blue-100 aria-selected:text-gray-700 aria-selected:opacity-70",
        day_disabled: "text-gray-200 opacity-50 cursor-not-allowed",
        day_range_middle:
          "aria-selected:bg-blue-100 aria-selected:text-gray-900",
        day_hidden: "invisible",
        ...classNames,
      }}
      components={{
        Chevron: (props) => {
          if (props.orientation === "left") {
            return <ChevronLeft className="h-4 w-4" />;
          }
          return <ChevronRight className="h-4 w-4" />;
        },
      }}
      {...props}
    />
  );
}
Calendar.displayName = "Calendar";

export { Calendar };
