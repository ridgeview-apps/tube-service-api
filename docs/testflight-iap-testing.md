# TestFlight In-App Purchase Testing

Use this guide when testing in-app purchases in a TestFlight build with Sandbox Apple Accounts.

## Overview

TestFlight uses your normal Apple ID for beta app access, but in-app purchase sandbox testing may require a separate Sandbox Apple Account.

The practical setup is to treat the device as having two modes:

- **TestFlight mode**: signed in with your normal Apple ID to install or update the beta app.
- **Purchase testing mode**: signed out of Media & Purchases, then signed in with a Sandbox Apple Account under Developer settings.

Signing out of **Media & Purchases** may also sign you out of TestFlight. That is expected. The installed beta app should remain usable. You only need to sign back into TestFlight when installing or updating the beta build.

## 1. Create Sandbox Apple Accounts

Create multiple Sandbox Apple Accounts in App Store Connect so each test scenario has its own purchase history.

If using Gmail, plus-address aliases can be used so all emails arrive in the same inbox:

```text
yourname+iap.fresh.uk@gmail.com
yourname+iap.active.uk@gmail.com
yourname+iap.expired.uk@gmail.com
yourname+iap.billing.uk@gmail.com
yourname+iap.fresh.us@gmail.com
```

Add each alias as a separate sandbox tester:

```text
App Store Connect > Users and Access > Sandbox > Add Sandbox Apple Account
```

Important:

- Use email addresses that are not already Apple Accounts.
- Once created, sandbox tester details such as name, email, and password cannot be edited.
- Store the account details securely in a password manager.
- Do not reuse your real Apple ID password.

## 2. Recommended Sandbox Account Purposes

Use separate accounts for different purchase states:

```text
fresh   = first-time purchase flow
active  = already subscribed or already purchased
expired = cancelled or expired subscription
billing = billing retry, failed renewal, or interrupted payment testing
region  = storefront, currency, or regional availability testing
```

## 3. Install or Update the TestFlight Build

Use your normal Apple ID for TestFlight access:

1. Sign into your normal Apple ID on the device.
2. Open TestFlight.
3. Accept the invite if needed.
4. Install or update the beta app.
5. Launch the app once to confirm it opens.

## 4. Switch to Purchase Testing Mode

After the TestFlight build is installed:

1. Open **Settings**.
2. Go to **[your name] > Media & Purchases**.
3. Tap **Sign Out**.
4. Go to **Settings > Developer > Sandbox Apple Account**.
5. Sign in with the Sandbox Apple Account for the scenario being tested.

## 5. Run the Purchase Test

1. Open the installed TestFlight app.
2. Run the in-app purchase flow.
3. Confirm the expected result in the app.
4. Record which Sandbox Apple Account was used.

## 6. Switch Scenarios

To test another purchase state, sign out of the current Sandbox Apple Account and sign in with the Sandbox Apple Account for the next scenario.

For example:

```text
yourname+iap.fresh.uk@gmail.com
yourname+iap.active.uk@gmail.com
yourname+iap.expired.uk@gmail.com
yourname+iap.billing.uk@gmail.com
```

## 7. Return to Normal TestFlight Mode

When a new beta build needs to be installed or updated:

1. Open **Settings**.
2. Go to **[your name] > Media & Purchases**.
3. Sign in with your normal Apple ID.
4. Open TestFlight.
5. Install or update the beta build.

After updating, switch back to purchase testing mode if more in-app purchase testing is needed.

## Tester Note

Signing out of **Media & Purchases** may sign you out of TestFlight. This is expected.

The installed TestFlight app should remain available and usable. You only need to sign back into TestFlight when installing or updating the beta app.
