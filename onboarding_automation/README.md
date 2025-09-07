
# Onboarding Document Automation

This project automates the process of preparing and sending onboarding documents to new employees for their signature. 

It uses a Python script to fill PDF templates and a self-hosted [DocuSeal](https://docuseal.co/) instance to handle the legally binding e-signatures, providing a free alternative to services like PandaDoc or DocuSign.

## How It Works

1.  **PDF Templates**: You provide a set of PDF document templates (e.g., employment contract, NDA).
2.  **Python Script**: A script reads the templates, fills in the employee's name, and saves new PDFs.
3.  **DocuSeal**: The script sends the filled PDFs to your DocuSeal server, which emails them to the employee for signing.
4.  **Completion**: Once signed, you receive a notification and the completed document from DocuSeal.

---

## Setup and Usage

Follow these steps to get the system running.

### **Step 1: Prepare Your PDF Templates (Crucial!)**

This is the most important manual step. The script can only fill PDFs that have **fillable form fields**.

-   **Requirement**: Each of your 12 template PDFs must be edited to include a fillable text field where the employee's name should go.
-   **Field Name**: The script is hard-coded to look for a field with the exact name `employee_name`.
-   **How to Create Fields**: You can use a tool like [Adobe Acrobat Pro](https://www.adobe.com/acrobat/how-to/create-fillable-pdf-forms.html) or a free online PDF editor to add these form fields to your PDFs.

**Action:** Place your 12 modified PDF templates into the `/onboarding_automation/templates/` directory.

### **Step 2: Deploy DocuSeal**

You need to host the DocuSeal server. We recommend using [Railway.app](https://railway.app/) for its simplicity and free tier.

1.  **Create a Railway Account**: Sign up at [railway.app](https://railway.app/) using your GitHub account.
2.  **Create a GitHub Repo**: Create a new, empty GitHub repository (e.g., `my-docuseal-instance`).
3.  **Upload `docker-compose.yml`**: Upload the `docker-compose.yml` file from the `/onboarding_automation/docuseal/` directory into your new GitHub repository.
4.  **Deploy on Railway**: 
    -   Create a new project on Railway and connect it to the GitHub repository you just made.
    -   Railway will automatically detect the `docker-compose.yml` and deploy DocuSeal.
    -   It will give you a public URL (e.g., `https://my-docuseal-prod-123.up.railway.app`). This is your `DOCUSEAL_URL`.
5.  **Configure DocuSeal**:
    -   Open your DocuSeal URL.
    -   Create your admin account.
    -   Go to `Settings -> Email` and configure it to send emails (see previous instructions on using a Google App Password).
    -   Go to `Settings -> API Keys` and create a new API key. This is your `DOCUSEAL_API_KEY`.

### **Step 3: Run the Automation Script**

1.  **Install Dependencies**: Open your terminal and navigate to the `onboarding_automation/app` directory:
    ```bash
    cd onboarding_automation/app
    pip install -r requirements.txt
    ```

2.  **Set Environment Variables**: For security, the script reads your API key and URL from environment variables. Set them in your terminal:
    ```bash
    export DOCUSEAL_URL="https://your-docuseal-instance.up.railway.app"
    export DOCUSEAL_API_KEY="your_12345_api_key_from_docuseal"
    ```

3.  **Run the Script**: Execute the `main.py` script with the new employee's details.
    ```bash
    python main.py --name "John Doe" --email "john.doe@example.com" --owner-email "your.email@company.com"
    ```

The script will now fill all 12 templates and send them for signature. You're all set!
