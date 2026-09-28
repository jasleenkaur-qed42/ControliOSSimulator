### Test Case: TC_ORDER_001 - Add a product to cart and complete checkout

| Attribute | Details |
| :--- | :--- |
| **Test Scenario** | Verify that a product can be added to the cart from the product list, its quantity adjusted, and an order placed end-to-end through checkout, payment, and order confirmation. |
| **Priority** | High |
| **Pre-conditions** | The user is on the app's Home tab, with an empty cart. (If a product is already in the cart, its detail screen shows quantity +/- controls instead of an "Add to cart" button — this flow assumes starting from an empty cart.) |

#### Test Execution Steps

| Step | Action | Expected Result | Status (Pass/Fail) |
| :--- | :--- | :--- | :--- |
| **1** | Tap "Products" in the bottom tab navigation. | The product list screen appears | |
| **2** | Wait for the products to appear.Tap the first product in the product list, the product is a card with an image and a name. | The product detail screen appears for the selected product. | |
| **3** | Tap the "Add to cart" button at the bottom of the product detail screen. | A quantity stepper with "+" and "-" buttons, and a "View cart" button, appear in the same position, replacing the "Add to cart" button. The quantity shows 1. | |
| **4** | Tap the "Increase quantity" button. | The quantity value increases from 1 to 2. | |
| **5** | Tap the "View cart" button. | The cart screen appears, showing the added product in the list with a quantity of 2. | |
| **6** | Tap the "Checkout" button. | The checkout screen appears with an address form. The "Continue to payment" button is disabled. | |
| **7** | Tap the "Full name" field. | The field becomes focused/editable. | |
| **8** | Type "Jane Philip". | The text appears in the Full name field. | |
| **9** | Tap the "Phone" field. | The field becomes focused/editable. | |
| **10** | Type "1234567890". | The text appears in the Phone field. | |
| **11** | Tap the "Address line 1" field. | The field becomes focused/editable. | |
| **12** | Type "56 city center". | The text appears in the Address line 1 field. | |
| **13** | Tap the "Address line 2" field. | The field becomes focused/editable. | |
| **14** | Type "New york city". | The text appears in the Address line 2 field. | |
| **15** | Tap the "City" field. | The field becomes focused/editable. | |
| **16** | Type "New York". | The text appears in the City field. | |
| **17** | Tap the "State / region" field. | The field becomes focused/editable. | |
| **18** | Type "America". | The text appears in the State field. | |
| **19** | Tap the "Postal code" field. | The field becomes focused/editable. | |
| **20** | Type "356722". | The text appears in the Postal code field. | |
| **21** | Tap the "Country" field. | The field becomes focused/editable. | |
| **22** | Type "USA". | The text appears in the Country field, and once all required address fields are filled, the "Continue to payment" button becomes enabled. | |
| **23** | Tap the "Continue to payment" button. | The checkout screen shows payment method options, including "Credit / Debit card". | |
| **24** | Tap the "Credit / Debit card" option. | The "Credit / Debit card" option becomes selected. | |
| **25** | Tap the "Pay" button. | An "Order placed" confirmation screen appears, showing an order ID, a "View order" button, and a "Continue shopping" button. | |
| **26** | Tap the "View order" button. | The View Order screen appears, showing the details of the product that was ordered. | |
| **27** | Tap "Back". | The previous "Order placed" confirmation screen appears again. | |
| **28** | Tap "Continue shopping". | The Product list screen appears. | |

#### Post-conditions
* The Products screen is visible, with "Products" active in the bottom tab navigation.
