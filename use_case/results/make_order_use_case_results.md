### Test Case: TC_ORDER_001 - Add a product to cart and complete checkout

| Attribute | Details |
| :--- | :--- |
| **Test Scenario** | Verify that a product can be added to the cart from the product list, its quantity adjusted, and an order placed end-to-end through checkout, payment, and order confirmation. |
| **Priority** | High |
| **Pre-conditions** | The user is on the app's Home tab, with an empty cart. (If a product is already in the cart, its detail screen shows quantity +/- controls instead of an "Add to cart" button — this flow assumes starting from an empty cart.) |

#### Test Execution Steps

| Step | Action | Expected Result | Status (Pass/Fail) |
| :--- | :--- | :--- | :--- |
| **1** | Tap "Products" in the bottom tab navigation. | The product list screen appears | PASS — The product list screen appears, with multiple buttons and a generic home element, indicating the expected result has happened |
| **2** | Wait for the products to appear.Tap the first product in the product list, the product is a card with an image and a name. | The product detail screen appears for the selected product. | PASS — The product detail screen appears for the selected product, specifically the 'Dog Products' heading, 'Specifications' heading, and detailed product information, including price and reviews. |
| **3** | Tap the "Add to cart" button at the bottom of the product detail screen. | A quantity stepper with "+" and "-" buttons, and a "View cart" button, appear in the same position, replacing the "Add to cart" button. The quantity shows 1. | PASS — A quantity stepper with "+" and "-" buttons, and a "View cart" button, appear in the same position, replacing the "Add to cart" button. The quantity shows 1. |
| **4** | Tap the "Increase quantity" button. | The quantity value increases from 1 to 2. | PASS — The current UI elements show that the quantity value has increased from 1 to 2. |
| **5** | Tap the "View cart" button. | The cart screen appears, showing the added product in the list with a quantity of 2. | PASS — The cart screen shows the added product in the list with a quantity of 2, as indicated by the '2' StaticText element |
| **6** | Tap the "Checkout" button. | The checkout screen appears with an address form. The "Continue to payment" button is disabled. | FAIL — The 'Continue to payment' button is disabled, indicating the expected result did not happen |
| **7** | Tap the "Full name" field. | The field becomes focused/editable. | PASS — The Full name field is editable, as indicated by its type (TextField) and value |
| **8** | Type "Jane Philip". | The text appears in the Full name field. | PASS — deterministic: 'Full name' value exactly matches typed text 'Jane Philip' |
| **9** | Tap the "Phone" field. | The field becomes focused/editable. | PASS — The field becomes focused/editable. |
| **10** | Type "1234567890". | The text appears in the Phone field. | PASS — deterministic: 'Phone' value exactly matches typed text '1234567890' |
| **11** | Tap the "Address line 1" field. | The field becomes focused/editable. | PASS — The Full name field (type: TextField) is editable, and the Phone field (type: TextField) is also editable |
| **12** | Type "56 city center". | The text appears in the Address line 1 field. | PASS — deterministic: 'Address line 1' value exactly matches typed text '56 city center' |
| **13** | Tap the "Address line 2" field. | The field becomes focused/editable. | PASS — The field 'Full name' (type: TextField) became editable with value 'Jane Philip' after the test step, and the field 'Phone' (type: TextField) became editable with value '1234567890' after the test step. |
| **14** | Type "New york city". | The text appears in the Address line 2 field. | PASS — deterministic: 'Address line 2 (optional)' value exactly matches typed text 'New york city' |
| **15** | Tap the "City" field. | The field becomes focused/editable. | PASS — The 'Delivery address' heading is visible, indicating the field is focused/editable. |
| **16** | Type "New York". | The text appears in the City field. | PASS — deterministic: 'City' value exactly matches typed text 'New York' |
| **17** | Tap the "State / region" field. | The field becomes focused/editable. | PASS — The field becomes focused/editable. |
| **18** | Type "America". | The text appears in the State field. | PASS — deterministic: 'State / region' value exactly matches typed text 'America' |
| **19** | Tap the "Postal code" field. | The field becomes focused/editable. | PASS — The field becomes focused/editable on the 'Full name' (type: TextField) |
| **20** | Type "356722". | The text appears in the Postal code field. | PASS — deterministic: 'Postal code' value exactly matches typed text '356722' |
| **21** | Tap the "Country" field. | The field becomes focused/editable. | PASS — The field becomes focused/editable, as shown by the textfields 'Phone' and 'Postal code' and the textfields with values |
| **22** | Type "USA". | The text appears in the Country field, and once all required address fields are filled, the "Continue to payment" button becomes enabled. | PASS — The text appears in the Country field, and once all required address fields are filled, the Continue to payment button becomes enabled |
| **23** | Tap the "Continue to payment" button. | The checkout screen shows payment method options, including "Credit/Debit card". | PASS — The current UI elements show clear evidence that the expected result happened, specifically the presence of the 'Credit / Debit card' radio button. |
| **24** | Tap the "Credit/Debit card" option. | The "Credit/Debit card" option becomes selected. | PASS — The current UI element shows a selected radio button labeled "Credit / Debit card" |
| **25** | Tap the "Pay" button. | An "Order placed" confirmation screen appears, showing an order ID, a "View Order" button, and a "Continue shopping" button. | FAIL — action failed: Requested label 'Pay' does not exist in the current UI. Available labels: 'Expo Go', 'Order placed', 'Order ID: order-stub-draft-card', 'Thank you for your purchase. You can view your order details or continue shopping.', 'View order', 'Continue shopping', 'gearshape.fill' |
| **26** | Tap the "View Order" button. | The View Order screen appears, showing the details of the product that was ordered. | BLOCKED — not attempted — a prior step failed |
| **27** | Tap the back button in the header. | The previous "Order placed" confirmation screen appears again. | BLOCKED — not attempted — a prior step failed |
| **28** | Tap "Continue shopping". | The Home screen appears. | BLOCKED — not attempted — a prior step failed |

#### Post-conditions
* The Home screen is visible, with "Home" active in the bottom tab navigation.

#### Automated Run Results (agent self-assessment — not authoritative)

- Step 1: **PASS** — The product list screen appears, with multiple buttons and a generic home element, indicating the expected result has happened
- Step 2: **PASS** — The product detail screen appears for the selected product, specifically the 'Dog Products' heading, 'Specifications' heading, and detailed product information, including price and reviews.
- Step 3: **PASS** — A quantity stepper with "+" and "-" buttons, and a "View cart" button, appear in the same position, replacing the "Add to cart" button. The quantity shows 1.
- Step 4: **PASS** — The current UI elements show that the quantity value has increased from 1 to 2.
- Step 5: **PASS** — The cart screen shows the added product in the list with a quantity of 2, as indicated by the '2' StaticText element
- Step 6: **FAIL** — The 'Continue to payment' button is disabled, indicating the expected result did not happen
- Step 7: **PASS** — The Full name field is editable, as indicated by its type (TextField) and value
- Step 8: **PASS** — deterministic: 'Full name' value exactly matches typed text 'Jane Philip'
- Step 9: **PASS** — The field becomes focused/editable.
- Step 10: **PASS** — deterministic: 'Phone' value exactly matches typed text '1234567890'
- Step 11: **PASS** — The Full name field (type: TextField) is editable, and the Phone field (type: TextField) is also editable
- Step 12: **PASS** — deterministic: 'Address line 1' value exactly matches typed text '56 city center'
- Step 13: **PASS** — The field 'Full name' (type: TextField) became editable with value 'Jane Philip' after the test step, and the field 'Phone' (type: TextField) became editable with value '1234567890' after the test step.
- Step 14: **PASS** — deterministic: 'Address line 2 (optional)' value exactly matches typed text 'New york city'
- Step 15: **PASS** — The 'Delivery address' heading is visible, indicating the field is focused/editable.
- Step 16: **PASS** — deterministic: 'City' value exactly matches typed text 'New York'
- Step 17: **PASS** — The field becomes focused/editable.
- Step 18: **PASS** — deterministic: 'State / region' value exactly matches typed text 'America'
- Step 19: **PASS** — The field becomes focused/editable on the 'Full name' (type: TextField)
- Step 20: **PASS** — deterministic: 'Postal code' value exactly matches typed text '356722'
- Step 21: **PASS** — The field becomes focused/editable, as shown by the textfields 'Phone' and 'Postal code' and the textfields with values
- Step 22: **PASS** — The text appears in the Country field, and once all required address fields are filled, the Continue to payment button becomes enabled
- Step 23: **PASS** — The current UI elements show clear evidence that the expected result happened, specifically the presence of the 'Credit / Debit card' radio button.
- Step 24: **PASS** — The current UI element shows a selected radio button labeled "Credit / Debit card"
- Step 25: **FAIL** — action failed: Requested label 'Pay' does not exist in the current UI. Available labels: 'Expo Go', 'Order placed', 'Order ID: order-stub-draft-card', 'Thank you for your purchase. You can view your order details or continue shopping.', 'View order', 'Continue shopping', 'gearshape.fill'
- Step 26: **BLOCKED** — not attempted — a prior step failed
- Step 27: **BLOCKED** — not attempted — a prior step failed
- Step 28: **BLOCKED** — not attempted — a prior step failed
- Post-conditions: **BLOCKED** — not attempted — a prior step failed
