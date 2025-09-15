// Schedule Map Interactive Functionality

(function() {
  const scheduleData = {
    slots: new Set(), // Store selected time slots as "day-time" strings
    client: null
  };

  // Time slot mapping
  const timeSlots = {
    'early-morning': { start: '06:00', end: '09:00', label: '6-9 AM' },
    'late-morning': { start: '09:00', end: '12:00', label: '9-12 PM' },
    'early-afternoon': { start: '12:00', end: '15:00', label: '12-3 PM' },
    'late-afternoon': { start: '15:00', end: '18:00', label: '3-6 PM' }
  };

  const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

  function initializeScheduleMap() {
    // Add click handlers to all time slots
    document.querySelectorAll('.time-slot').forEach(slot => {
      slot.addEventListener('click', function() {
        toggleTimeSlot(this);
      });
    });

    // Load initial data if available
    loadScheduleFromState();
  }

  function toggleTimeSlot(slotElement) {
    const day = slotElement.dataset.day;
    const time = slotElement.dataset.time;
    const slotKey = `${day}-${time}`;

    if (slotElement.classList.contains('selected')) {
      // Deselect
      slotElement.classList.remove('selected');
      scheduleData.slots.delete(slotKey);
    } else {
      // Select
      slotElement.classList.add('selected');
      scheduleData.slots.add(slotKey);
    }

    // Update visual feedback
    updateSlotVisuals();
    
    // Check for conflicts
    checkConflicts();
  }

  function updateSlotVisuals() {
    // Add visual feedback and animations
    document.querySelectorAll('.time-slot.selected').forEach(slot => {
      if (!slot.querySelector('.check-icon')) {
        const checkIcon = document.createElement('div');
        checkIcon.className = 'check-icon';
        checkIcon.innerHTML = '✓';
        slot.appendChild(checkIcon);
      }
    });

    document.querySelectorAll('.time-slot:not(.selected)').forEach(slot => {
      const checkIcon = slot.querySelector('.check-icon');
      if (checkIcon) {
        checkIcon.remove();
      }
    });
  }

  function loadScheduleFromState() {
    // Load from global state if available
    if (window.state && window.state.schedule) {
      const schedule = window.state.schedule;
      
      // Convert old format to new format if needed
      if (schedule.times && schedule.days) {
        convertLegacySchedule(schedule);
      }
    }
  }

  function convertLegacySchedule(legacySchedule) {
    // Convert the old time-based schedule to slot-based
    if (!legacySchedule.times || !legacySchedule.days) return;

    legacySchedule.days.forEach(day => {
      const dayKey = day.toLowerCase();
      
      // Map times to our new time slots
      legacySchedule.times.forEach(timeArray => {
        const hour = parseInt(timeArray[0]);
        const ampm = timeArray[2];
        const hour24 = ampm === 'PM' && hour !== 12 ? hour + 12 : (ampm === 'AM' && hour === 12 ? 0 : hour);
        
        let timeSlot;
        if (hour24 >= 6 && hour24 < 9) timeSlot = 'early-morning';
        else if (hour24 >= 9 && hour24 < 12) timeSlot = 'late-morning';
        else if (hour24 >= 12 && hour24 < 15) timeSlot = 'early-afternoon';
        else if (hour24 >= 15 && hour24 < 18) timeSlot = 'late-afternoon';
        
        if (timeSlot) {
          const slotKey = `${dayKey}-${timeSlot}`;
          scheduleData.slots.add(slotKey);
          
          // Update visual
          const slotElement = document.querySelector(`[data-day="${dayKey}"][data-time="${timeSlot}"]`);
          if (slotElement) {
            slotElement.classList.add('selected');
          }
        }
      });
    });

    updateSlotVisuals();
  }

  async function checkConflicts() {
    if (!scheduleData.slots.size) return;

    // Convert our slot data to format expected by conflict API
    const timeData = convertSlotsToTimeData();
    
    try {
      const response = await fetch('/api/conflicts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client: window.state?.currentClient || null,
          times: timeData.times,
          days: timeData.days
        })
      });

      if (response.ok) {
        const data = await response.json();
        updateConflictVisuals(data.results || []);
      }
    } catch (error) {
      console.error('Error checking conflicts:', error);
    }
  }

  function convertSlotsToTimeData() {
    const times = [];
    const activeDays = new Set();

    scheduleData.slots.forEach(slotKey => {
      const [day, timeSlot] = slotKey.split('-');
      activeDays.add(day);
      
      const timeInfo = timeSlots[timeSlot];
      if (timeInfo) {
        const [hour, minute] = timeInfo.start.split(':');
        const hour12 = hour === '00' ? 12 : (hour > 12 ? hour - 12 : parseInt(hour));
        const ampm = hour >= 12 ? 'PM' : 'AM';
        
        times.push([hour12.toString(), minute, ampm]);
      }
    });

    return {
      times: times,
      days: Array.from(activeDays).map(day => 
        day.charAt(0).toUpperCase() + day.slice(1)
      )
    };
  }

  function updateConflictVisuals(conflicts) {
    // Clear previous conflict indicators
    document.querySelectorAll('.time-slot').forEach(slot => {
      slot.classList.remove('conflict');
    });

    // Apply conflict indicators based on API response
    conflicts.forEach((conflict, index) => {
      if (conflict && conflict.conflict) {
        // Find corresponding slot elements - this is simplified
        // In a real implementation, you'd need more sophisticated mapping
        document.querySelectorAll('.time-slot.selected').forEach((slot, slotIndex) => {
          if (slotIndex === index) {
            slot.classList.add('conflict');
          }
        });
      }
    });
  }

  // Save schedule function
  async function saveSchedule() {
    if (!window.state?.currentClient) {
      alert('Please select a client first');
      return;
    }

    const timeData = convertSlotsToTimeData();
    
    try {
      const response = await fetch(`/api/client/${encodeURIComponent(window.state.currentClient)}/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client: window.state.currentClient,
          times: timeData.times,
          days: timeData.days,
          slots: Array.from(scheduleData.slots) // Also save our new format
        })
      });

      if (response.ok) {
        showNotification('Schedule saved successfully!', 'success');
        // Refresh overview
        if (window.loadOverview) {
          window.loadOverview();
        }
      } else {
        showNotification('Failed to save schedule', 'error');
      }
    } catch (error) {
      console.error('Error saving schedule:', error);
      showNotification('Error saving schedule', 'error');
    }
  }

  function showNotification(message, type) {
    // Simple notification system
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 12px 20px;
      border-radius: 8px;
      color: white;
      font-weight: 600;
      z-index: 1000;
      transition: all 0.3s ease;
      background: ${type === 'success' ? '#10b981' : '#ef4444'};
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.style.opacity = '0';
      notification.style.transform = 'translateY(-20px)';
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }

  // Initialize when DOM is ready
  document.addEventListener('DOMContentLoaded', function() {
    initializeScheduleMap();

    // Bind save button
    const saveBtn = document.getElementById('saveScheduleBtn');
    if (saveBtn) {
      saveBtn.addEventListener('click', saveSchedule);
    }

    // Bind refresh conflicts button
    const refreshBtn = document.getElementById('refreshConflictsBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', checkConflicts);
    }
  });

  // Expose functions to global scope for integration
  window.scheduleMap = {
    saveSchedule,
    checkConflicts,
    loadScheduleFromState,
    scheduleData
  };
})();
