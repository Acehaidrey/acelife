/** Create a constants file. */

const Platform = {
  SLICE: 'SLICE',
  MENUSTAR: 'MENUSTAR',
  DOORDASH: 'DOORDASH',
  MENUFY: 'MENUFY',
  EATSTREET: "EATSTREET",
  GRUBHUB: "GRUBHUB"
};

const PaymentType = {
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

SIMILARITY_THRESHOLD = 80;

module.exports = {
    Platform,
    PaymentType,
    recordType,
    keyType,
    SIMILARITY_THRESHOLD
}