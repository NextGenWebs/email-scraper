# AWS EC2 Deployment Guide

Complete guide to deploy Email Scraper on AWS EC2 with CI/CD.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│  ┌─────────────┐    ┌─────────────────────────────────────┐    │
│  │   GitHub    │───▶│            EC2 Instance              │    │
│  │  (CI/CD)    │    │  ┌─────────────────────────────────┐ │    │
│  └─────────────┘    │  │         Docker Compose          │ │    │
│                     │  │  ┌─────┐ ┌─────┐ ┌───────────┐  │ │    │
│                     │  │  │Flask│ │Redis│ │PostgreSQL │  │ │    │
│                     │  │  │:5000│ │:6379│ │   :5432   │  │ │    │
│                     │  │  └─────┘ └─────┘ └───────────┘  │ │    │
│                     │  │  ┌───────────┐ ┌─────────────┐  │ │    │
│                     │  │  │  Celery   │ │   Flower    │  │ │    │
│                     │  │  │  Workers  │ │   :5555     │  │ │    │
│                     │  │  └───────────┘ └─────────────┘  │ │    │
│                     │  └─────────────────────────────────┘ │    │
│                     └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Step 1: Create EC2 Instance

### 1.1 Launch Instance
1. Go to AWS Console → EC2 → Launch Instance
2. Configure:
   - **Name**: `email-scraper`
   - **AMI**: Ubuntu Server 22.04 LTS
   - **Instance Type**: `t3.medium` (minimum) or `t3.large` (recommended)
   - **Key Pair**: Create new or use existing (save the .pem file!)
   - **Storage**: 30 GB gp3

### 1.2 Security Group Rules
Create/configure security group with these inbound rules:

| Type  | Port | Source    | Description       |
|-------|------|-----------|-------------------|
| SSH   | 22   | Your IP   | SSH access        |
| HTTP  | 80   | 0.0.0.0/0 | Web traffic       |
| HTTPS | 443  | 0.0.0.0/0 | Secure web traffic|
| Custom| 5000 | 0.0.0.0/0 | Flask app (temp)  |
| Custom| 5555 | Your IP   | Flower monitoring |

### 1.3 Elastic IP (Optional but Recommended)
1. Go to EC2 → Elastic IPs → Allocate
2. Associate with your instance
3. This gives you a static IP that won't change

## Step 2: Connect to EC2

```bash
# Make key file secure
chmod 400 your-key.pem

# Connect via SSH
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
```

## Step 3: Initial Server Setup

Run on EC2:

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install Git
sudo apt-get install -y git

# Log out and back in for docker group
exit
```

Reconnect:
```bash
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
```

## Step 4: Clone Repository

```bash
# Create app directory
mkdir -p ~/email-scraper
cd ~/email-scraper

# Clone your repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git .
```

## Step 5: Configure Environment

```bash
# Create production .env file
nano .env
```

Add these contents (update values!):

```env
# Database
DB_USER=postgres
DB_PASSWORD=YOUR_STRONG_PASSWORD_HERE
DB_NAME=email_scraper

# Redis (internal Docker network)
REDIS_URL=redis://redis:6379/0

# Security - Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SESSION_SECRET=YOUR_GENERATED_SECRET_HERE

# Production settings
SESSION_COOKIE_SECURE=true
PREFERRED_URL_SCHEME=https
PROXY_FIX=true
FLASK_DEBUG=false

# Celery
CELERY_CONCURRENCY=4
```

Save: `Ctrl+X`, `Y`, `Enter`

## Step 6: Start Application

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f web
```

## Step 7: Setup GitHub CI/CD

### 7.1 Add GitHub Secrets

Go to your GitHub repo → Settings → Secrets and variables → Actions

Add these secrets:

| Secret Name | Value |
|-------------|-------|
| `EC2_HOST` | Your EC2 public IP or Elastic IP |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | Contents of your .pem file |
| `DOCKER_USERNAME` | Your Docker Hub username |
| `DOCKER_PASSWORD` | Your Docker Hub password/token |

### 7.2 Create Docker Hub Account
1. Go to https://hub.docker.com
2. Create account
3. Create access token: Account Settings → Security → New Access Token

### 7.3 Deploy SSH Key to EC2
The GitHub Actions workflow needs SSH access. Your existing key pair works.

## Step 8: Test Deployment

1. Make a small change to your code
2. Commit and push to `main` branch
3. Go to GitHub → Actions to watch the deployment
4. After deployment, visit `http://YOUR_EC2_IP:5000`

## Step 9: Setup Domain & SSL (Optional)

### 9.1 Point Domain to EC2
In your domain registrar (GoDaddy, Namecheap, etc.):
- Add A record pointing to your EC2 Elastic IP

### 9.2 Setup Nginx with SSL

```bash
# Install Certbot
sudo apt-get install -y certbot python3-certbot-nginx nginx

# Create Nginx config
sudo nano /etc/nginx/sites-available/email-scraper
```

Add:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/email-scraper /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## Useful Commands

```bash
# View all containers
docker-compose ps

# View logs
docker-compose logs -f [service_name]

# Restart services
docker-compose restart

# Stop all
docker-compose down

# Rebuild and restart
docker-compose up -d --build

# Enter container shell
docker-compose exec web bash

# Database backup
docker-compose exec db pg_dump -U postgres email_scraper > backup.sql

# Check disk space
df -h

# Check memory
free -m
```

## Troubleshooting

### Container won't start
```bash
docker-compose logs web
docker-compose logs celery_scrape
```

### Database connection error
```bash
docker-compose exec db psql -U postgres -c "\l"
```

### Out of memory
```bash
# Check memory usage
docker stats

# Reduce Celery concurrency in .env
CELERY_CONCURRENCY=2
```

### Permission denied
```bash
sudo chown -R $USER:$USER ~/email-scraper
```

## Costs Estimate

| Service | Specs | Monthly Cost |
|---------|-------|--------------|
| EC2 t3.medium | 2 vCPU, 4GB RAM | ~$30 |
| EC2 t3.large | 2 vCPU, 8GB RAM | ~$60 |
| EBS Storage | 30GB gp3 | ~$3 |
| Elastic IP | (free while attached) | $0 |
| **Total** | | **~$33-63/month** |

## Security Checklist

- [ ] Change default database password
- [ ] Generate strong SESSION_SECRET
- [ ] Restrict SSH to your IP only
- [ ] Enable SSL/HTTPS
- [ ] Setup automatic security updates
- [ ] Regular backups
- [ ] Monitor logs for suspicious activity
