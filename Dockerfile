# Dockerfile
# ----------
# Builds a container image for the CyberShield platform itself.
# (The service-based challenges CS-04/CS-06 get their OWN separate
# Dockerfiles inside challenges/cs04_vulnerable_portal/ and
# challenges/cs06_compromised_server/ -- see the README in each.)

FROM python:3.11-slim

WORKDIR /app

# Copy just requirements.txt first (not the whole project) so Docker
# can cache this "pip install" layer -- it only reruns when
# requirements.txt actually changes, making rebuilds much faster.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the project in.
COPY . .

RUN mkdir -p /app/database

EXPOSE 5000

CMD ["python", "run.py"]
