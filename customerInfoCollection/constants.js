/** Create a constants file. */

const Platform = {
  SLICE: 'SLICE',
  MENUSTAR: 'MENUSTAR',
  DOORDASH: 'DOORDASH',
  MENUFY: 'MENUFY',
  EATSTREET: "EATSTREET",
  GRUBHUB: "GRUBHUB",
  TOAST: "TOAST",
  BRYGID: "BRYGID",
  SPEEDLINE: "SPEEDLINE",
};

const storeType = {
    AMECI: 'AMECI',
    AROMA: 'AROMA'
}

const paymentType = {
    CASH: 'CASH',
    CREDIT: 'CREDIT'
}

const keyType = {
    NAME: 'name',
    PHONE: 'phoneNumber'
}

const recordType = {
    TRANSACTION: 'TRANSACTION',
    CUSTOMER: 'CUSTOMER',
    ERROR: 'ERROR'
}

const orderType = {
    DELIVERY: 'DELIVERY',
    PICKUP: 'PICKUP'
}

const errorType = {
    PLATFORM: 'Parsing issue with platform',
    STORE_NAME: 'Parsing issue with storeName',
    PAYMENT_TYPE: 'Parsing issue with paymentType',
    ORDER_DATE: 'Parsing issue with orderDate',
    ORDER_TYPE: 'Parsing issue with orderType',
    ORDER_AMOUNT: 'Parsing issue with orderAmount',
    ORDER_ID: 'Parsing issue with orderId',
    CUSTOMER_NAME: 'Parsing issue with customerName',
    CUSTOMER_NUMBER: 'Parsing issue with customerNumber',
    CUSTOMER_EMAIL: 'Parsing issue with customerEmail',
    CUSTOMER_ADDRESS: 'Parsing issue with customerAddress',
    ZIPCODE: 'Parsing issue with zipcode',
    CITY: 'Parsing issue with city',
    STATE: 'Parsing issue with state',
    STREET: 'Parsing issue with street',
    JSON_BODY: 'Parsing issue with getting JSON body',
    NOT_TRANSACTION_EMAIL: 'Email record is not a transaction email'
}

const States = {
    FAILED: 'FAILED',
    SUCCESS: 'SUCCESS',
    NOT_RUN: 'NOT_RUN'
}

/**
 * Threshold percentage to get the similarity overlap between values.
 * @type {number}
 */
SIMILARITY_THRESHOLD = 80;

module.exports = {
    Platform,
    States,
    paymentType,
    recordType,
    keyType,
    errorType,
    orderType,
    storeType,
    SIMILARITY_THRESHOLD
}