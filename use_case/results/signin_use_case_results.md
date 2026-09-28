### Test Case: TC_SIGNIN_001 - Sign in with email and password, and continue as guest

| Attribute | Details |
| :--- | :--- |
| **Test Scenario** | Verify that tapping Sign in shows a sign-in form, that entering credentials and submitting is possible, and that a guest can also continue from the same form. |
| **Priority** | High |
| **Pre-conditions** | The user is on the app's Home tab. |

#### Test Execution Steps

| Step | Action | Expected Result | Status (Pass/Fail) |
| :--- | :--- | :--- | :--- |
| **1** | Tap the "Sign in" link. | A sign-in form appears with Username or email and Password fields, and a Continue as guest option. | PASS — The current UI elements show clear evidence the expected result happened, including a sign-in form with Username or email and Password fields, and a Continue as guest option. |
| **2** | Tap "Continue as guest". | The app returns to the Home tab content. | PASS — The UI shows clear evidence the app returned to the Home tab content, with headings like 'Everyday essentials, thoughtfully made.' and 'Home' at the top. |
| **3** | Tap the "Sign in" link. | A sign-in form appears with Username or email and Password fields, and a Continue as guest option. | PASS — The expected result did not happen because the Continue as guest option is not present, but the Continue as guest option is actually present, therefore the verdict is true |
| **4** | Tap the "Username or email" field. | The field becomes focused/editable. | PASS — The field became focused/editable, as indicated by the visible text in the TextField. |
| **5** | Type "user1@xyz.com". | The email text appears in the Username or email field. | PASS — deterministic: 'Username or email' value exactly matches typed text 'user1@xyz.com' |
| **6** | Tap the "Password" field. | The field becomes focused/editable. | PASS — The current UI elements show clear evidence that the field became focused and editable, specifically the TextField with the value 'user1@xyz.com'. |
| **7** | Type "user1". | The password is entered (masked) in the Password field. | PASS — The password is entered (masked) in the Password field |
| **8** | Tap the "Sign in" button to submit the credentials. | Either an error message appears (if the credentials are invalid) or the user is signed in and redirected to the Home tab. | FAIL — The application is signed in and redirected to the Home tab, which does not match the expected error message if credentials are invalid. |

#### Post-conditions
* The Home tab's "Shop now" button is visible again.

#### Automated Run Results (agent self-assessment — not authoritative)

- Step 1: **PASS** — The current UI elements show clear evidence the expected result happened, including a sign-in form with Username or email and Password fields, and a Continue as guest option.
- Step 2: **PASS** — The UI shows clear evidence the app returned to the Home tab content, with headings like 'Everyday essentials, thoughtfully made.' and 'Home' at the top.
- Step 3: **PASS** — The expected result did not happen because the Continue as guest option is not present, but the Continue as guest option is actually present, therefore the verdict is true
- Step 4: **PASS** — The field became focused/editable, as indicated by the visible text in the TextField.
- Step 5: **PASS** — deterministic: 'Username or email' value exactly matches typed text 'user1@xyz.com'
- Step 6: **PASS** — The current UI elements show clear evidence that the field became focused and editable, specifically the TextField with the value 'user1@xyz.com'.
- Step 7: **PASS** — The password is entered (masked) in the Password field
- Step 8: **FAIL** — The application is signed in and redirected to the Home tab, which does not match the expected error message if credentials are invalid.
- Post-conditions: **PASS** — deterministic: expected label(s) ['Shop now'] all present in current UI
