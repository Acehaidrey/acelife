/** Create a constants file. */

const Platform = {
  SLICE: 'SLICE',
  MENUSTAR: 'MENUSTAR',
  DOORDASH: 'DOORDASH',
  MENUFY: 'MENUFY',
  EATSTREET: "EATSTREET",
  GRUBHUB: "GRUBHUB"
};

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
    CUSTOMER: 'CUSTOMER'
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
}


SIMILARITY_THRESHOLD = 80;

module.exports = {
    Platform,
    paymentType,
    recordType,
    keyType,
    errorType,
    orderType,
    SIMILARITY_THRESHOLD
}