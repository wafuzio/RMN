# Calendar Popup - Porting Guide

This document contains all the necessary code and information to port the calendar event popup/dialog to another project.

## Overview

The calendar popup is a modal dialog for creating and editing calendar events. It's self-contained with embedded HTML structure, CSS styling, and JavaScript functionality.

---

## 1. Core HTML Structure

The popup is created dynamically via JavaScript. Here's the HTML structure:

```html
<div class="event-dialog">
  <div class="event-dialog-content">
    <h3 class="event-dialog-title">Event Details</h3>
    <form id="event-form">
      <div class="form-group">
        <label for="event-title">Title</label>
        <input type="text" id="event-title" required>
      </div>
      <div class="form-group">
        <label for="event-start">Start</label>
        <input type="datetime-local" id="event-start" required>
      </div>
      <div class="form-group">
        <label for="event-end">End</label>
        <input type="datetime-local" id="event-end" required>
      </div>
      <div class="form-group">
        <label for="event-location">Location</label>
        <input type="text" id="event-location" class="full-width-input">
      </div>
      <div class="form-group">
        <label for="event-calendar">Calendar</label>
        <select id="event-calendar" class="full-width-input">
          <option value="shared">Shared Calendar</option>
          <option value="dan">Dan's Calendar</option>
          <option value="katie">Katie's Calendar</option>
        </select>
      </div>
      <div class="form-group">
        <label for="event-description">Description</label>
        <textarea id="event-description"></textarea>
      </div>
      <div class="form-group">
        <label>
          <input type="checkbox" id="event-all-day">
          All day event
        </label>
      </div>
      <div class="dialog-buttons">
        <button type="button" class="btn-cancel">Cancel</button>
        <button type="submit" class="btn-save">Save</button>
        <button type="button" class="btn-delete" style="display:none;">Delete</button>
      </div>
    </form>
  </div>
</div>
```

---

## 2. CSS Styling

Complete styling for the popup modal:

```css
.event-dialog {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 1000;
}

.event-dialog-content {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: white;
  padding: 20px;
  border-radius: 8px;
  min-width: 320px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
}

.event-dialog-title {
  margin: 0 0 20px;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
}

.form-group input[type="text"],
.form-group input[type="datetime-local"],
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-sizing: border-box;
}

.form-group textarea {
  resize: vertical;
  min-height: 60px;
}

.dialog-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.dialog-buttons button {
  padding: 8px 16px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  background-color: #f0f0f0;
  color: #333;
  transition: background-color 0.2s;
}

.dialog-buttons button:hover {
  background-color: #e0e0e0;
}

.btn-save {
  background: #4a90e2;
  color: white;
}

.btn-save:hover {
  background: #357abd;
}

.btn-cancel {
  background: #f0f0f0;
}

.btn-delete {
  background: #dc3545;
  color: white;
}

.btn-delete:hover {
  background: #c82333;
}
```

---

## 3. JavaScript Implementation

### 3.1 Standalone Version (No Dependencies)

Here's a simplified, standalone version that doesn't rely on the CalendarSystem framework:

```javascript
const CalendarPopup = {
  eventDialog: null,
  eventForm: null,
  currentEventId: null,
  onSave: null, // Callback function for saving events
  onDelete: null, // Callback function for deleting events

  /**
   * Initialize the popup
   * @param {Object} callbacks - { onSave: function(eventData), onDelete: function(eventId) }
   */
  init(callbacks = {}) {
    this.onSave = callbacks.onSave || this.defaultSaveHandler;
    this.onDelete = callbacks.onDelete || this.defaultDeleteHandler;
    this.createEventDialog();
  },

  /**
   * Create the dialog element and inject into DOM
   */
  createEventDialog() {
    if (this.eventDialog) return;

    const dialog = document.createElement('div');
    dialog.className = 'event-dialog';
    dialog.innerHTML = `
      <div class="event-dialog-content">
        <h3 class="event-dialog-title">Event Details</h3>
        <form id="event-form">
          <div class="form-group">
            <label for="event-title">Title</label>
            <input type="text" id="event-title" required>
          </div>
          <div class="form-group">
            <label for="event-start">Start</label>
            <input type="datetime-local" id="event-start" required>
          </div>
          <div class="form-group">
            <label for="event-end">End</label>
            <input type="datetime-local" id="event-end" required>
          </div>
          <div class="form-group">
            <label for="event-location">Location</label>
            <input type="text" id="event-location" class="full-width-input">
          </div>
          <div class="form-group">
            <label for="event-calendar">Calendar</label>
            <select id="event-calendar" class="full-width-input">
              <option value="shared">Shared Calendar</option>
              <option value="personal">Personal Calendar</option>
            </select>
          </div>
          <div class="form-group">
            <label for="event-description">Description</label>
            <textarea id="event-description"></textarea>
          </div>
          <div class="form-group">
            <label>
              <input type="checkbox" id="event-all-day">
              All day event
            </label>
          </div>
          <div class="dialog-buttons">
            <button type="button" class="btn-cancel">Cancel</button>
            <button type="submit" class="btn-save">Save</button>
            <button type="button" class="btn-delete" style="display:none;">Delete</button>
          </div>
        </form>
      </div>
    `;

    document.body.appendChild(dialog);
    this.eventDialog = dialog;
    this.eventForm = dialog.querySelector('#event-form');

    // Inject CSS
    this.injectStyles();

    // Setup event listeners
    this.setupEventListeners();
  },

  /**
   * Inject CSS styles into document head
   */
  injectStyles() {
    if (document.getElementById('calendar-popup-styles')) return;

    const style = document.createElement('style');
    style.id = 'calendar-popup-styles';
    style.textContent = `
      .event-dialog {
        display: none;
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.5);
        z-index: 1000;
      }
      .event-dialog-content {
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        padding: 20px;
        border-radius: 8px;
        min-width: 320px;
        max-width: 90vw;
        max-height: 90vh;
        overflow-y: auto;
      }
      .event-dialog-title {
        margin: 0 0 20px;
      }
      .form-group {
        margin-bottom: 15px;
      }
      .form-group label {
        display: block;
        margin-bottom: 5px;
      }
      .form-group input[type="text"],
      .form-group input[type="datetime-local"],
      .form-group input[type="date"],
      .form-group select,
      .form-group textarea {
        width: 100%;
        padding: 8px;
        border: 1px solid #ddd;
        border-radius: 4px;
        box-sizing: border-box;
      }
      .form-group textarea {
        resize: vertical;
        min-height: 60px;
      }
      .dialog-buttons {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 20px;
      }
      .dialog-buttons button {
        padding: 8px 16px;
        border-radius: 4px;
        border: none;
        cursor: pointer;
        font-size: 14px;
        background-color: #f0f0f0;
        color: #333;
        transition: background-color 0.2s;
      }
      .dialog-buttons button:hover {
        background-color: #e0e0e0;
      }
      .btn-save {
        background: #4a90e2;
        color: white;
      }
      .btn-save:hover {
        background: #357abd;
      }
      .btn-cancel {
        background: #f0f0f0;
      }
      .btn-delete {
        background: #dc3545;
        color: white;
      }
      .btn-delete:hover {
        background: #c82333;
      }
    `;
    document.head.appendChild(style);
  },

  /**
   * Setup all event listeners
   */
  setupEventListeners() {
    if (!this.eventForm) return;

    // Form submission
    this.eventForm.addEventListener('submit', (e) => {
      e.preventDefault();
      this.saveEvent();
    });

    // Cancel button
    this.eventForm.querySelector('.btn-cancel').addEventListener('click', () => {
      this.hideEventDialog();
    });

    // Delete button
    this.eventForm.querySelector('.btn-delete').addEventListener('click', () => {
      this.deleteEvent();
    });

    // All-day checkbox toggle
    this.eventForm.querySelector('#event-all-day').addEventListener('change', (e) => {
      this.handleAllDayToggle(e.target.checked);
    });

    // Click outside to close
    this.eventDialog.addEventListener('click', (e) => {
      if (e.target === this.eventDialog) {
        this.hideEventDialog();
      }
    });
  },

  /**
   * Handle all-day checkbox toggle
   */
  handleAllDayToggle(isAllDay) {
    const startInput = this.eventForm.querySelector('#event-start');
    const endInput = this.eventForm.querySelector('#event-end');

    if (!startInput || !endInput) return;

    // Get current values
    let startValue = startInput.value ? new Date(startInput.value) : new Date();
    let endValue = endInput.value ? new Date(endInput.value) : new Date(startValue);

    // Change input types
    if (isAllDay) {
      startInput.type = 'date';
      endInput.type = 'date';
      startInput.value = this.formatDate(startValue, true);
      endInput.value = this.formatDate(endValue, true);
    } else {
      startInput.type = 'datetime-local';
      endInput.type = 'datetime-local';
      startInput.value = this.formatDate(startValue, false);
      endInput.value = this.formatDate(endValue, false);
    }
  },

  /**
   * Show dialog for adding a new event
   * @param {Date|string} date - Initial date for the event
   */
  showAddEventDialog(date = new Date()) {
    if (!this.eventDialog) {
      this.createEventDialog();
    }

    this.currentEventId = null;

    // Show dialog
    this.eventDialog.style.display = 'block';

    // Hide delete button
    this.eventForm.querySelector('.btn-delete').style.display = 'none';

    // Parse date
    const startDate = new Date(date);
    const endDate = new Date(startDate.getTime() + 3600000); // +1 hour

    // Clear and set form fields
    this.eventForm.querySelector('#event-title').value = '';
    this.eventForm.querySelector('#event-start').value = this.formatDate(startDate, false);
    this.eventForm.querySelector('#event-end').value = this.formatDate(endDate, false);
    this.eventForm.querySelector('#event-location').value = '';
    this.eventForm.querySelector('#event-description').value = '';
    this.eventForm.querySelector('#event-all-day').checked = false;
    this.eventForm.querySelector('#event-start').type = 'datetime-local';
    this.eventForm.querySelector('#event-end').type = 'datetime-local';
  },

  /**
   * Show dialog for editing an existing event
   * @param {Object} event - Event object with properties: id, title, start, end, location, description, calendar, isAllDay
   */
  showEditEventDialog(event) {
    if (!this.eventDialog) {
      this.createEventDialog();
    }

    if (!event) {
      console.error('Invalid event object');
      return;
    }

    this.currentEventId = event.id;

    // Show dialog
    this.eventDialog.style.display = 'block';

    // Show delete button
    this.eventForm.querySelector('.btn-delete').style.display = 'block';

    // Parse dates
    const startDate = new Date(event.start || new Date());
    const endDate = new Date(event.end || new Date(startDate.getTime() + 3600000));
    const isAllDay = event.isAllDay || event.allDay || false;

    // Set form fields
    this.eventForm.querySelector('#event-title').value = event.title || '';
    this.eventForm.querySelector('#event-location').value = event.location || '';
    this.eventForm.querySelector('#event-description').value = event.description || '';
    this.eventForm.querySelector('#event-all-day').checked = isAllDay;

    // Set calendar dropdown
    const calendarSelect = this.eventForm.querySelector('#event-calendar');
    if (event.calendar) {
      calendarSelect.value = event.calendar;
    }

    // Set date fields based on all-day status
    const startInput = this.eventForm.querySelector('#event-start');
    const endInput = this.eventForm.querySelector('#event-end');

    if (isAllDay) {
      startInput.type = 'date';
      endInput.type = 'date';
      startInput.value = this.formatDate(startDate, true);
      endInput.value = this.formatDate(endDate, true);
    } else {
      startInput.type = 'datetime-local';
      endInput.type = 'datetime-local';
      startInput.value = this.formatDate(startDate, false);
      endInput.value = this.formatDate(endDate, false);
    }
  },

  /**
   * Hide the dialog
   */
  hideEventDialog() {
    if (this.eventDialog) {
      this.eventDialog.style.display = 'none';
      this.currentEventId = null;
    }
  },

  /**
   * Save event (calls the onSave callback)
   */
  async saveEvent() {
    if (!this.eventForm) return;

    // Gather form data
    const eventData = {
      id: this.currentEventId,
      title: this.eventForm.querySelector('#event-title').value.trim(),
      start: new Date(this.eventForm.querySelector('#event-start').value).toISOString(),
      end: new Date(this.eventForm.querySelector('#event-end').value).toISOString(),
      location: this.eventForm.querySelector('#event-location').value.trim(),
      description: this.eventForm.querySelector('#event-description').value.trim(),
      calendar: this.eventForm.querySelector('#event-calendar').value,
      isAllDay: this.eventForm.querySelector('#event-all-day').checked
    };

    // Validate
    if (!eventData.title) {
      alert('Please enter a title');
      return;
    }

    try {
      // Call the save callback
      if (this.onSave) {
        await this.onSave(eventData);
      }

      // Close dialog on success
      this.hideEventDialog();
    } catch (error) {
      console.error('Error saving event:', error);
      alert('Error saving event: ' + error.message);
    }
  },

  /**
   * Delete event (calls the onDelete callback)
   */
  async deleteEvent() {
    if (!this.currentEventId) return;

    if (!confirm('Are you sure you want to delete this event?')) {
      return;
    }

    try {
      // Call the delete callback
      if (this.onDelete) {
        await this.onDelete(this.currentEventId);
      }

      // Close dialog on success
      this.hideEventDialog();
    } catch (error) {
      console.error('Error deleting event:', error);
      alert('Error deleting event: ' + error.message);
    }
  },

  /**
   * Format date for input fields
   * @param {Date} date - Date object
   * @param {boolean} isAllDay - Whether this is an all-day event
   * @returns {string} Formatted date string
   */
  formatDate(date, isAllDay = false) {
    if (!date) return '';

    const d = new Date(date);
    if (isNaN(d.getTime())) return '';

    if (isAllDay) {
      // Format as YYYY-MM-DD
      return d.toISOString().split('T')[0];
    } else {
      // Format as YYYY-MM-DDTHH:MM
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      const hours = String(d.getHours()).padStart(2, '0');
      const minutes = String(d.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    }
  },

  /**
   * Default save handler (override with your own)
   */
  defaultSaveHandler(eventData) {
    console.log('Event saved:', eventData);
    alert('Event saved! (This is a default handler - implement your own save logic)');
  },

  /**
   * Default delete handler (override with your own)
   */
  defaultDeleteHandler(eventId) {
    console.log('Event deleted:', eventId);
    alert('Event deleted! (This is a default handler - implement your own delete logic)');
  }
};
```

---

## 4. Usage Examples

### 4.1 Basic Usage

```javascript
// Initialize the popup with custom save/delete handlers
CalendarPopup.init({
  onSave: async (eventData) => {
    console.log('Saving event:', eventData);
    // Your save logic here (API call, database update, etc.)
    // Example:
    // await fetch('/api/events', {
    //   method: eventData.id ? 'PUT' : 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify(eventData)
    // });
  },
  onDelete: async (eventId) => {
    console.log('Deleting event:', eventId);
    // Your delete logic here
    // Example:
    // await fetch(`/api/events/${eventId}`, { method: 'DELETE' });
  }
});

// Show popup for creating a new event
CalendarPopup.showAddEventDialog(new Date());

// Show popup for editing an existing event
CalendarPopup.showEditEventDialog({
  id: '123',
  title: 'Team Meeting',
  start: '2025-10-26T10:00:00Z',
  end: '2025-10-26T11:00:00Z',
  location: 'Conference Room A',
  description: 'Weekly team sync',
  calendar: 'shared',
  isAllDay: false
});
```

### 4.2 Integration with Calendar Click Events

```javascript
// Example: Open popup when clicking on a calendar date
document.querySelectorAll('.calendar-day').forEach(dayCell => {
  dayCell.addEventListener('click', (e) => {
    const date = dayCell.dataset.date; // Assuming date is stored in data attribute
    CalendarPopup.showAddEventDialog(new Date(date));
  });
});

// Example: Open popup when clicking on an event
document.querySelectorAll('.calendar-event').forEach(eventEl => {
  eventEl.addEventListener('click', (e) => {
    const eventData = JSON.parse(eventEl.dataset.event); // Assuming event data is stored
    CalendarPopup.showEditEventDialog(eventData);
  });
});
```

---

## 5. Key Features

### 5.1 All-Day Event Toggle
- Automatically switches between `datetime-local` and `date` input types
- Preserves date values when toggling

### 5.2 Date Formatting
- Handles ISO 8601 date strings
- Converts to local timezone for display
- Formats correctly for HTML5 date/datetime-local inputs

### 5.3 Validation
- Required fields: title, start date
- End date defaults to 1 hour after start if not provided
- Date validation to prevent invalid dates

### 5.4 Responsive Design
- Modal overlay with centered dialog
- Max width/height constraints for mobile
- Scrollable content area

---

## 6. Customization Options

### 6.1 Calendar Options
Modify the calendar dropdown options in the HTML:
```javascript
<select id="event-calendar">
  <option value="work">Work Calendar</option>
  <option value="personal">Personal Calendar</option>
  <option value="family">Family Calendar</option>
</select>
```

### 6.2 Styling
All CSS is in the `injectStyles()` method. Customize colors, spacing, etc.:
- Primary button color: `.btn-save { background: #4a90e2; }`
- Delete button color: `.btn-delete { background: #dc3545; }`
- Modal overlay opacity: `.event-dialog { background: rgba(0,0,0,0.5); }`

### 6.3 Additional Fields
Add custom fields by inserting into the form HTML:
```html
<div class="form-group">
  <label for="event-priority">Priority</label>
  <select id="event-priority">
    <option value="low">Low</option>
    <option value="medium">Medium</option>
    <option value="high">High</option>
  </select>
</div>
```

Then capture in `saveEvent()`:
```javascript
eventData.priority = this.eventForm.querySelector('#event-priority').value;
```

---

## 7. Dependencies

### None Required!
This is a standalone implementation with:
- ✅ No external libraries
- ✅ No framework dependencies
- ✅ Pure vanilla JavaScript
- ✅ HTML5 date/datetime inputs
- ✅ Modern CSS (flexbox, transforms)

### Browser Compatibility
- Chrome/Edge: Full support
- Firefox: Full support
- Safari: Full support
- IE11: Not supported (uses modern JS features)

---

## 8. Original Implementation Notes

The original implementation in this codebase:
- Uses a `CalendarSystem` module framework for dependency management
- Integrates with Google Apps Script for backend persistence
- Has additional features for iCloud calendar sync
- Includes more complex date handling for timezone conversions

The standalone version provided above removes these dependencies while maintaining core functionality.

---

## 9. Quick Start Checklist

- [ ] Copy the `CalendarPopup` JavaScript object into your project
- [ ] Initialize with `CalendarPopup.init({ onSave: yourSaveFunction, onDelete: yourDeleteFunction })`
- [ ] Customize calendar dropdown options for your use case
- [ ] Implement save/delete handlers to persist data
- [ ] Add click handlers to trigger `showAddEventDialog()` or `showEditEventDialog()`
- [ ] Test all-day event toggle functionality
- [ ] Customize styling to match your design system

---

## 10. File Reference

**Original Source File:** `/Users/dan.maguire/Documents/Projects/tasklist/src/Modules/Calendar/Calendar_Events.html`

Key sections:
- Lines 213-362: Dialog creation and styling
- Lines 364-422: Event listeners setup
- Lines 430-496: Add event dialog
- Lines 498-622: Edit event dialog
- Lines 625-630: Hide dialog
- Lines 770-985: Save event logic
- Lines 1081-1109: Date formatting utilities

---

## Support & Troubleshooting

### Common Issues:

1. **Dialog not appearing**: Check z-index conflicts with other modals
2. **Date format errors**: Ensure dates are valid ISO 8601 strings
3. **Save not working**: Verify onSave callback is properly defined
4. **Styling conflicts**: Add more specific CSS selectors or use !important

### Debug Mode:
Add console logging to track behavior:
```javascript
console.log('Event data:', eventData);
console.log('Current event ID:', this.currentEventId);
```
