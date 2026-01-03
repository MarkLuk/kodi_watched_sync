NOTIFICATION_INFO = "info"

class Dialog:
    def ok(self, heading, message):
        print(f"[Dialog] OK: {heading} - {message}")

    def select(self, heading, options):
        print(f"[Dialog] Select: {heading} - Options: {options}")
        # Return 0 (Import) or 1 (Export) for testing logic
        # Ideally, we can control this via a global variable or injection
        return getattr(Dialog, 'mock_selection', -1)

    def notification(self, heading, message, icon, time):
        print(f"[Dialog] Notification: {heading} - {message}")
