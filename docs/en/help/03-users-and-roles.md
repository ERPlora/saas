# Users, roles and PIN access

ERPlora separates the Cloud account from the users who work inside a Hub:

- The **Cloud account** uses email, password and any required second factor to identify the account holder.
- A **Hub user** is local to one Hub and receives a role, permissions and an optional 4-digit PIN for trusted-device access.

## How PIN access works

PIN is a quick return method, not the first credential on an unknown device.

1. Sign in with email and password on the new device.
2. Select **Trust this device**.
3. Choose and confirm a 4-digit PIN.
4. On later visits, select your user and enter that PIN.

If the device is no longer trusted, the PIN entry is not offered. Use the **Email** tab, sign in again and recreate device trust. Never share a PIN between employees.

## Employees and login users

An employee or staff record does not automatically grant access to the Hub. A person who needs to sign in must also have a Hub user with an assigned role. This keeps operational staff data separate from authentication and permissions.

Administrators manage access from **Employees**:

- Create or update Hub users.
- Assign roles.
- Review the permissions supplied by installed modules.
- Disable access when a person should no longer enter the Hub.
- Manage API keys where that feature is available.

## Roles and permissions

Roles are local to the Hub. Their permissions come from the core Hub and the modules currently installed, so the available permission list changes with the Hub's capabilities.

Use the least access required for the job. Only owner or administrator roles should change Hub-wide settings, users, module permissions or fiscal credentials.

## If a user cannot sign in

- **PIN screen is missing:** the device is not trusted or no PIN-enabled Hub user is available.
- **PIN is rejected:** confirm the selected user; then use email sign-in if the PIN must be reset.
- **A page is missing:** verify the user's role and the permissions of the relevant module.
- **The user no longer exists:** an administrator must recreate or reactivate the Hub user; cached browser data cannot restore one.
