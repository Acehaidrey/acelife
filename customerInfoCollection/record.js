/**
 * File containing the Record types.
 */

class TransactionRecord {
  constructor(platform, orderDate) {
    this.platform = platform;
    this.orderDate = orderDate;
    this.storeName = null;
    this.orderType = null;
    this.error = false;
    this.errorReason = [];
    this.customerName = null;
    this.customerNumber = null;
    this.customerEmail = null;
    this.customerAddress = null;
    this.street = null;
    this.city = null;
    this.state = null;
    this.zipcode = null;
    this.orderAmount = 0;
    this.paymentType = null;
    this.orderId = null;
    }
}


class CustomerRecord {
  constructor(store, number) {
    this.platforms = new Set();
    this.storeName = store;
    this.customerNames = new Set();
    this.customerNumber = number;
    this.lastOrderDate = null;
    this.firstOrderDate = null;
    this.customerAddresses = new Set();
    this.customerEmails = new Set();
    this.orderCount = 0;
    this.totalSpend = 0;
  }
}

module.exports = {
	CustomerRecord,
	TransactionRecord
};