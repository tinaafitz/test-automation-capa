import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
import yaml
import os
from datetime import datetime


class EmailNotificationService:
    """Service for sending email notifications for provisioning jobs"""

    def __init__(self):
        self.config = self._load_config()
        self.smtp_server = self.config.get("smtp_server", "")
        self.smtp_port = self.config.get("smtp_port", 587)
        self.smtp_username = self.config.get("smtp_username", "")
        self.smtp_password = self.config.get("smtp_password", "")
        self.from_email = self.config.get("from_email", "")
        self.to_emails = self.config.get("to_emails", [])
        self.use_tls = self.config.get("use_tls", True)

    def _load_config(self) -> Dict[str, Any]:
        """Load notification config from vars/notification_config.yml"""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "vars",
            "notification_config.yml",
        )

        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    return yaml.safe_load(f) or {}
            else:
                return self._default_config()
        except Exception as e:
            print(f"Error loading notification config: {e}")
            return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """Return default email configuration"""
        return {
            "email_enabled": False,
            "smtp_server": "",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "from_email": "",
            "to_emails": [],
            "use_tls": True,
        }

    def reload_config(self):
        """Reload configuration from file"""
        self.config = self._load_config()
        self.smtp_server = self.config.get("smtp_server", "")
        self.smtp_port = self.config.get("smtp_port", 587)
        self.smtp_username = self.config.get("smtp_username", "")
        self.smtp_password = self.config.get("smtp_password", "")
        self.from_email = self.config.get("from_email", "")
        self.to_emails = self.config.get("to_emails", [])
        self.use_tls = self.config.get("use_tls", True)

    def send_provisioning_notification(self, job_data: dict, status: str) -> bool:
        """
        Send email notification for provisioning job

        Args:
            job_data: Dictionary containing job information
            status: Job status ('started', 'completed', 'failed')

        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        if not self.config.get("email_enabled") or not self.smtp_server:
            print("Email notifications disabled or SMTP not configured")
            return False

        if not self.to_emails:
            print("No recipient email addresses configured")
            return False

        subject, html_body, text_body = self._build_email_content(job_data, status)
        return self._send_email(subject, html_body, text_body)

    def _build_email_content(self, job_data: dict, status: str) -> tuple:
        """Build email subject and body content"""
        cluster_name = job_data.get("cluster_name", "Unknown")
        region = job_data.get("region", "N/A")
        version = job_data.get("version", "N/A")
        job_id = job_data.get("job_id", "N/A")

        if status == "completed":
            return self._build_success_email(cluster_name, region, version, job_id)
        elif status == "failed":
            return self._build_failure_email(cluster_name, region, job_data, job_id)
        elif status == "started":
            return self._build_started_email(cluster_name, region, version, job_id)
        else:
            return self._build_generic_email(cluster_name, status, job_data)

    def _build_success_email(
        self, cluster_name: str, region: str, version: str, job_id: str
    ) -> tuple:
        """Build success notification email"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        subject = f"ROSA Cluster Provisioned Successfully - {cluster_name}"

        html_body = f"""
        <html>
          <body style="margin: 0; padding: 0; background-color: #f0fdf4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 24px;">
              <div style="background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(16, 185, 129, 0.12);">

                <!-- Header -->
                <div style="background: linear-gradient(135deg, #059669 0%, #10b981 50%, #34d399 100%); padding: 32px 32px 28px; text-align: center;">
                  <div style="font-size: 48px; margin-bottom: 8px;">&#9989;</div>
                  <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.3px;">
                    Cluster Provisioned Successfully
                  </h1>
                  <p style="color: rgba(255,255,255,0.85); margin: 6px 0 0; font-size: 14px;">Your ROSA HCP cluster is ready to use</p>
                </div>

                <!-- Progress Bar -->
                <div style="padding: 0 32px;">
                  <div style="display: flex; justify-content: space-between; padding: 20px 0 8px; font-size: 11px; color: #6b7280;">
                    <span>Network</span><span>IAM Roles</span><span>Cluster</span><span style="color: #059669; font-weight: 700;">Ready</span>
                  </div>
                  <div style="background: #d1fae5; border-radius: 8px; height: 8px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #059669, #10b981, #34d399); width: 100%; height: 100%; border-radius: 8px;"></div>
                  </div>
                </div>

                <!-- Cluster Details -->
                <div style="padding: 24px 32px;">
                  <table style="width: 100%; border-collapse: separate; border-spacing: 0; background: #f0fdf4; border-radius: 12px; overflow: hidden;">
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; width: 130px; border-bottom: 1px solid #d1fae5; font-size: 14px;">Cluster</td>
                      <td style="padding: 14px 20px; font-family: 'SF Mono', Monaco, Consolas, monospace; color: #059669; font-weight: 600; border-bottom: 1px solid #d1fae5; font-size: 14px;">{cluster_name}</td>
                    </tr>
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; border-bottom: 1px solid #d1fae5; font-size: 14px;">Region</td>
                      <td style="padding: 14px 20px; color: #4b5563; border-bottom: 1px solid #d1fae5; font-size: 14px;">{region}</td>
                    </tr>
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; border-bottom: 1px solid #d1fae5; font-size: 14px;">Version</td>
                      <td style="padding: 14px 20px; color: #4b5563; border-bottom: 1px solid #d1fae5; font-size: 14px;">{version}</td>
                    </tr>
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; font-size: 14px;">Status</td>
                      <td style="padding: 14px 20px; font-size: 14px;">
                        <span style="background: #059669; color: #fff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">Ready</span>
                      </td>
                    </tr>
                  </table>
                </div>

                <!-- Next Steps -->
                <div style="padding: 0 32px 24px;">
                  <div style="background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%); border-radius: 12px; padding: 20px 24px; border: 1px solid #bfdbfe;">
                    <h3 style="margin: 0 0 12px; color: #1e40af; font-size: 15px; font-weight: 700;">&#128640; Next Steps</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                      <tr>
                        <td style="padding: 6px 0; color: #374151; font-size: 14px;">
                          <span style="color: #3b82f6; margin-right: 8px;">&#10095;</span> Access via OpenShift Console
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; color: #374151; font-size: 14px;">
                          <span style="color: #3b82f6; margin-right: 8px;">&#10095;</span> Configure cluster-admin access
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; color: #374151; font-size: 14px;">
                          <span style="color: #3b82f6; margin-right: 8px;">&#10095;</span> Deploy your applications
                        </td>
                      </tr>
                    </table>
                  </div>
                </div>

                <!-- Footer -->
                <div style="padding: 16px 32px; background: #f9fafb; border-top: 1px solid #e5e7eb; text-align: center;">
                  <p style="margin: 0; color: #9ca3af; font-size: 11px;">
                    Job ID: {job_id} &nbsp;&#8226;&nbsp; Completed: {timestamp}
                  </p>
                  <p style="margin: 4px 0 0; color: #d1d5db; font-size: 10px;">CAPA Automation Framework</p>
                </div>

              </div>
            </div>
          </body>
        </html>
        """

        text_body = f"""
ROSA Cluster Provisioned Successfully

Cluster: {cluster_name}
Region: {region}
Version: {version}
Status: Ready

Next Steps:
- Access via OpenShift Console
- Configure cluster-admin access
- Deploy your applications

Job ID: {job_id} | Completed: {timestamp}
        """

        return subject, html_body, text_body

    def _build_failure_email(
        self, cluster_name: str, region: str, job_data: dict, job_id: str
    ) -> tuple:
        """Build failure notification email"""
        error = job_data.get("error", "Unknown error")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Truncate error if too long
        if len(error) > 500:
            error = error[:497] + "..."

        subject = f"ROSA Cluster Provisioning Failed - {cluster_name}"

        html_body = f"""
        <html>
          <body style="margin: 0; padding: 0; background-color: #fef2f2; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 24px;">
              <div style="background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(239, 68, 68, 0.12);">

                <!-- Header -->
                <div style="background: linear-gradient(135deg, #b91c1c 0%, #dc2626 50%, #ef4444 100%); padding: 32px 32px 28px; text-align: center;">
                  <div style="font-size: 48px; margin-bottom: 8px;">&#10060;</div>
                  <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.3px;">
                    Cluster Provisioning Failed
                  </h1>
                  <p style="color: rgba(255,255,255,0.85); margin: 6px 0 0; font-size: 14px;">Action required &mdash; see details below</p>
                </div>

                <!-- Cluster Details -->
                <div style="padding: 24px 32px 16px;">
                  <table style="width: 100%; border-collapse: separate; border-spacing: 0; background: #fef2f2; border-radius: 12px; overflow: hidden;">
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; width: 130px; border-bottom: 1px solid #fecaca; font-size: 14px;">Cluster</td>
                      <td style="padding: 14px 20px; font-family: 'SF Mono', Monaco, Consolas, monospace; color: #dc2626; font-weight: 600; border-bottom: 1px solid #fecaca; font-size: 14px;">{cluster_name}</td>
                    </tr>
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; font-size: 14px;">Region</td>
                      <td style="padding: 14px 20px; color: #4b5563; font-size: 14px;">{region}</td>
                    </tr>
                  </table>
                </div>

                <!-- Error Box -->
                <div style="padding: 0 32px 20px;">
                  <div style="background: #1e1e1e; border-radius: 12px; padding: 20px; border: 1px solid #374151;">
                    <div style="display: flex; align-items: center; margin-bottom: 12px;">
                      <span style="color: #ef4444; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">&#9888; Error Output</span>
                    </div>
                    <pre style="margin: 0; color: #fca5a5; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word;">{error}</pre>
                  </div>
                </div>

                <!-- Troubleshooting -->
                <div style="padding: 0 32px 24px;">
                  <div style="background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); border-radius: 12px; padding: 20px 24px; border: 1px solid #fbbf24;">
                    <h3 style="margin: 0 0 12px; color: #92400e; font-size: 15px; font-weight: 700;">&#128269; Troubleshooting</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                      <tr>
                        <td style="padding: 6px 0; color: #78350f; font-size: 14px;">
                          <span style="color: #d97706; margin-right: 8px;">&#10095;</span> Check task logs for details
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; color: #78350f; font-size: 14px;">
                          <span style="color: #d97706; margin-right: 8px;">&#10095;</span> Verify AWS credentials and permissions
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; color: #78350f; font-size: 14px;">
                          <span style="color: #d97706; margin-right: 8px;">&#10095;</span> Ensure subnet and VPC configuration
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; color: #78350f; font-size: 14px;">
                          <span style="color: #d97706; margin-right: 8px;">&#10095;</span> Check OpenShift Cluster Manager quota limits
                        </td>
                      </tr>
                    </table>
                  </div>
                </div>

                <!-- Footer -->
                <div style="padding: 16px 32px; background: #f9fafb; border-top: 1px solid #e5e7eb; text-align: center;">
                  <p style="margin: 0; color: #9ca3af; font-size: 11px;">
                    Job ID: {job_id} &nbsp;&#8226;&nbsp; Failed: {timestamp}
                  </p>
                  <p style="margin: 4px 0 0; color: #d1d5db; font-size: 10px;">CAPA Automation Framework</p>
                </div>

              </div>
            </div>
          </body>
        </html>
        """

        text_body = f"""
ROSA Cluster Provisioning Failed

Cluster: {cluster_name}
Region: {region}

Error:
{error}

Troubleshooting:
- Check task logs for details
- Verify AWS credentials and permissions
- Ensure subnet and VPC configuration
- Check OpenShift Cluster Manager quota limits

Job ID: {job_id} | Failed: {timestamp}
        """

        return subject, html_body, text_body

    def _build_started_email(
        self, cluster_name: str, region: str, version: str, job_id: str
    ) -> tuple:
        """Build started notification email"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        subject = f"ROSA Cluster Provisioning Started - {cluster_name}"

        html_body = f"""
        <html>
          <body style="margin: 0; padding: 0; background-color: #ecfeff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 24px;">
              <div style="background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(8, 145, 178, 0.12);">

                <!-- Header -->
                <div style="background: linear-gradient(135deg, #0e7490 0%, #0891b2 50%, #06b6d4 100%); padding: 32px 32px 28px; text-align: center;">
                  <div style="font-size: 48px; margin-bottom: 8px;">&#128640;</div>
                  <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.3px;">
                    Cluster Provisioning Started
                  </h1>
                  <p style="color: rgba(255,255,255,0.85); margin: 6px 0 0; font-size: 14px;">Estimated time: ~17 minutes</p>
                </div>

                <!-- Progress Bar -->
                <div style="padding: 0 32px;">
                  <div style="display: flex; justify-content: space-between; padding: 20px 0 8px; font-size: 11px; color: #6b7280;">
                    <span style="color: #0891b2; font-weight: 700;">Network</span><span>IAM Roles</span><span>Cluster</span><span>Ready</span>
                  </div>
                  <div style="background: #e0f2fe; border-radius: 8px; height: 8px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #0e7490, #0891b2, #22d3ee); width: 15%; height: 100%; border-radius: 8px;"></div>
                  </div>
                </div>

                <!-- Cluster Details -->
                <div style="padding: 24px 32px;">
                  <table style="width: 100%; border-collapse: separate; border-spacing: 0; background: #ecfeff; border-radius: 12px; overflow: hidden;">
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; width: 130px; border-bottom: 1px solid #a5f3fc; font-size: 14px;">Cluster</td>
                      <td style="padding: 14px 20px; font-family: 'SF Mono', Monaco, Consolas, monospace; color: #0e7490; font-weight: 600; border-bottom: 1px solid #a5f3fc; font-size: 14px;">{cluster_name}</td>
                    </tr>
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; border-bottom: 1px solid #a5f3fc; font-size: 14px;">Region</td>
                      <td style="padding: 14px 20px; color: #4b5563; border-bottom: 1px solid #a5f3fc; font-size: 14px;">{region}</td>
                    </tr>
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; border-bottom: 1px solid #a5f3fc; font-size: 14px;">Version</td>
                      <td style="padding: 14px 20px; color: #4b5563; border-bottom: 1px solid #a5f3fc; font-size: 14px;">{version}</td>
                    </tr>
                    <tr>
                      <td style="padding: 14px 20px; font-weight: 600; color: #374151; font-size: 14px;">Status</td>
                      <td style="padding: 14px 20px; font-size: 14px;">
                        <span style="background: linear-gradient(135deg, #0891b2, #06b6d4); color: #fff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;">Provisioning</span>
                      </td>
                    </tr>
                  </table>
                </div>

                <!-- What's Happening -->
                <div style="padding: 0 32px 24px;">
                  <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border-radius: 12px; padding: 20px 24px; border: 1px solid #7dd3fc;">
                    <h3 style="margin: 0 0 12px; color: #0c4a6e; font-size: 15px; font-weight: 700;">&#9881; What's happening</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                      <tr>
                        <td style="padding: 6px 0; color: #0c4a6e; font-size: 14px;">
                          <span style="color: #0891b2; margin-right: 8px;">1.</span> Creating VPC and network via CloudFormation
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; color: #0c4a6e; font-size: 14px;">
                          <span style="color: #0891b2; margin-right: 8px;">2.</span> Configuring IAM roles and OIDC provider
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; color: #0c4a6e; font-size: 14px;">
                          <span style="color: #0891b2; margin-right: 8px;">3.</span> Provisioning ROSA HCP control plane
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 0; color: #0c4a6e; font-size: 14px;">
                          <span style="color: #0891b2; margin-right: 8px;">4.</span> Waiting for cluster readiness
                        </td>
                      </tr>
                    </table>
                  </div>
                </div>

                <!-- Footer -->
                <div style="padding: 16px 32px; background: #f9fafb; border-top: 1px solid #e5e7eb; text-align: center;">
                  <p style="margin: 0; color: #9ca3af; font-size: 11px;">
                    Job ID: {job_id} &nbsp;&#8226;&nbsp; Started: {timestamp}
                  </p>
                  <p style="margin: 4px 0 0; color: #d1d5db; font-size: 10px;">CAPA Automation Framework</p>
                </div>

              </div>
            </div>
          </body>
        </html>
        """

        text_body = f"""
ROSA Cluster Provisioning Started

Cluster: {cluster_name}
Region: {region}
Version: {version}
Status: Provisioning

What's happening:
1. Creating VPC and network via CloudFormation
2. Configuring IAM roles and OIDC provider
3. Provisioning ROSA HCP control plane
4. Waiting for cluster readiness

Estimated time: ~17 minutes

Job ID: {job_id} | Started: {timestamp}
        """

        return subject, html_body, text_body

    def _build_generic_email(self, cluster_name: str, status: str, job_data: dict) -> tuple:
        """Build generic notification email for other statuses"""
        subject = f"ROSA Cluster Update - {cluster_name}"

        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
              <h2>ROSA Cluster Update</h2>
              <p>Cluster <strong>{cluster_name}</strong> status: <strong>{status}</strong></p>
            </div>
          </body>
        </html>
        """

        text_body = f"ROSA Cluster Update\n\nCluster {cluster_name} status: {status}"

        return subject, html_body, text_body

    def _send_email(self, subject: str, html_body: str, text_body: str) -> bool:
        """
        Send email via SMTP

        Args:
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)

            # Attach both plain text and HTML versions
            part1 = MIMEText(text_body, "plain")
            part2 = MIMEText(html_body, "html")
            msg.attach(part1)
            msg.attach(part2)

            # Connect to SMTP server and send
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)

            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)

            server.sendmail(self.from_email, self.to_emails, msg.as_string())
            server.quit()

            print("Email notification sent successfully")
            return True

        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    def test_connection(self) -> dict:
        """
        Test SMTP connection

        Returns:
            dict: Result with success status and message
        """
        if not self.smtp_server:
            return {"success": False, "message": "SMTP server not configured"}

        if not self.to_emails:
            return {"success": False, "message": "No recipient email addresses configured"}

        try:
            # Test connection
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)

            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)

            # Send test email
            subject = "Email Notification Test - CAPA Automation"
            html_body = """
            <html>
              <body style="margin: 0; padding: 0; background-color: #f0fdf4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                <div style="max-width: 600px; margin: 0 auto; padding: 24px;">
                  <div style="background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(16, 185, 129, 0.12);">
                    <div style="background: linear-gradient(135deg, #059669 0%, #10b981 50%, #34d399 100%); padding: 32px; text-align: center;">
                      <div style="font-size: 48px; margin-bottom: 8px;">&#9989;</div>
                      <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700;">Email Test Successful</h1>
                    </div>
                    <div style="padding: 32px; text-align: center;">
                      <p style="color: #374151; font-size: 16px; margin: 0;">Your email integration is working correctly!</p>
                      <p style="color: #9ca3af; font-size: 13px; margin: 12px 0 0;">You will receive notifications for cluster provisioning events.</p>
                    </div>
                    <div style="padding: 16px 32px; background: #f9fafb; border-top: 1px solid #e5e7eb; text-align: center;">
                      <p style="margin: 0; color: #d1d5db; font-size: 10px;">CAPA Automation Framework</p>
                    </div>
                  </div>
                </div>
              </body>
            </html>
            """
            text_body = "Email Notification Test\n\nYour email integration is working correctly!\nYou will receive notifications for cluster provisioning events."

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            server.sendmail(self.from_email, self.to_emails, msg.as_string())
            server.quit()

            return {"success": True, "message": "Test email sent successfully"}

        except Exception as e:
            return {"success": False, "message": f"Failed to send test email: {str(e)}"}
