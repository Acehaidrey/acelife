/**
 * File containing the Record types.
 */

class TransactionRecord {
  constructor(platform, orderDate) {
    this.platform = platform;
    this.storeName = null;
    this.customerName = null;
    this.customerNumber = null;
    this.customerEmail = null;
    this.customerAddress = null;
    this.street = null;
    this.city = null;
    this.state = null;
    this.zipcode = null;
    this.orderAmount = 0;
    this.orderType = null;
    this.orderDate = orderDate;
    this.orderId = null;
    this.paymentType = null;
    this.error = false;
    this.errorReason = [];
  }
}


class CustomerRecord {
  constructor(store, number) {
    this.platforms = new Set();
    this.storeName = store;
    this.customerNumber = number;
    this.customerNames = new Set();
    this.customerAddresses = new Set();
    this.customerEmails = new Set();
    this.lastOrderDate = null;
    this.firstOrderDate = null;
    this.orderCount = 0;
    this.totalSpend = 0;
  }
}

module.exports = {CustomerRecord, TransactionRecord};