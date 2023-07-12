# Use an official Python runtime as the base image
FROM python:3.9

# Label the author of project
LABEL authors="ahaidrey"

# update the install
RUN apt-get update

# Install Unzip
RUN apt-get install -y unzip

# Install Chrome WebDriver
RUN CHROMEDRIVER_VERSION=`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE` && \
    mkdir -p /opt/chromedriver-$CHROMEDRIVER_VERSION && \
    curl -sS -o /tmp/chromedriver_linux64.zip http://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip && \
    unzip -qq /tmp/chromedriver_linux64.zip -d /opt/chromedriver-$CHROMEDRIVER_VERSION && \
    rm /tmp/chromedriver_linux64.zip && \
    chmod +x /opt/chromedriver-$CHROMEDRIVER_VERSION/chromedriver && \
    ln -fs /opt/chromedriver-$CHROMEDRIVER_VERSION/chromedriver /usr/local/bin/chromedriver

# Install Google Chrome
RUN curl -sS -o - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list && \
    apt-get -yqq update && \
    apt-get -yqq install google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Install Git
RUN apt-get install -y git

# Install Nano
RUN apt-get install -y nano

# Copy the requirements.txt file to the container
COPY requirements.txt .

# Create a virtual environment
RUN python3 -m venv venv

# Activate the virtual environment
ENV PATH="/app/venv/bin:$PATH"

# Upgrade pip
RUN pip3 install --no-cache-dir --upgrade pip

# Install the required Python packages
RUN pip3 install --no-cache-dir -r requirements.txt

# Setup env flag that running in GCP is prod
ENV GCP_ENV=true

# Set the command to accept arguments
CMD ["python", "main.py"]

# Set the command to run your Python script
#  python main.py -s 2023/06/01 -e 2023/06/30 -p restaurant_depot -n aroma


docker run -v "$(pwd)":/code provider-reports python /code/main.py -s 2023/06/01 -e 2023/06/30 -p restaurant_depot -n aroma
