### Test Case: TC_SIGNIN_001 - Sign in with email and password, and continue as guest

| Attribute | Details |
| :--- | :--- |
| **Test Scenario** | Verify that tapping Sign in shows a sign-in form, that entering credentials and submitting is possible, and that a guest can also continue from the same form. |
| **Priority** | High |
| **Pre-conditions** | The user is on the app's Home tab. |

#### Test Execution Steps

| Step | Action | Expected Result | Status (Pass/Fail) |
| :--- | :--- | :--- | :--- |
| **1** | Tap the "Sign in" link. | A sign-in form appears with Username or email and Password fields, and a Continue as guest option. | |
| **2** | Tap "Continue as guest". | The app returns to the Home tab content. | |
| **3** | Tap the "Sign in" link. | A sign-in form appears with Username or email and Password fields, and a Continue as guest option. | |
| **4** | Tap the "Username or email" field. | The field becomes focused/editable. | |
| **5** | Type "user1@xyz.com". | The email text appears in the Username or email field. | |
| **6** | Tap the "Password" field. | The field becomes focused/editable. | |
| **7** | Type "user1". | The password is entered (masked) in the Password field. | |
| **8** | Tap the "Sign in" button to submit the credentials. | Either an error message appears (if the credentials are invalid) or the user is signed in and redirected to the Home tab. | |

#### Post-conditions
* The Home tab's "Shop now" button is visible again.
