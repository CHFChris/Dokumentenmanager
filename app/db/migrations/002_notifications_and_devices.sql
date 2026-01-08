-- 002: UI-Toasts + Sicherheitsmails + Login-Device-Tracking

-- Users: Einstellungen
ALTER TABLE users
  ADD COLUMN ui_notifications_enabled TINYINT(1) NOT NULL DEFAULT 1,
  ADD COLUMN security_email_new_device_enabled TINYINT(1) NOT NULL DEFAULT 1;

-- Login-Devices
CREATE TABLE IF NOT EXISTS login_devices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  fingerprint_hash CHAR(64) NOT NULL,
  first_seen_at DATETIME(6) NOT NULL,
  last_seen_at DATETIME(6) NOT NULL,
  last_ip VARCHAR(64) NULL,
  last_user_agent VARCHAR(512) NULL,
  CONSTRAINT fk_login_devices_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY ux_login_devices_user_fingerprint (user_id, fingerprint_hash),
  INDEX idx_login_devices_user (user_id)
) ENGINE=InnoDB;
