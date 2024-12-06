FROM python:3.10.5

# Create the application directory
RUN mkdir /usr/src/app
WORKDIR /usr/src/app

# Copy only requirements.txt first for efficient layer caching
COPY requirements.txt /usr/src/app/

# Install Python dependencies
RUN pip install -r requirements.txt

# Copy the source code from the `src` directory
COPY src /usr/src/app

# Define the command to run your app
CMD ["python3", "app.py"]
