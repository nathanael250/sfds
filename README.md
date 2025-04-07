# Agro Management System

A Flask-based web application for managing agricultural products, stock, and sales.

## Features

- User roles: Agrodealer, Sector Agronomy Officer (SAO), and Manager Director (MD)
- Stock management with approval workflow
- Customer lookup and price calculation based on land size
- Financial reporting and transaction tracking
- Invoice upload and management

## Prerequisites

- Python 3.8 or higher
- MySQL 5.7 or higher
- pip (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd agro-management
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```

4. Create a MySQL database:
```sql
CREATE DATABASE agro_management;
```

5. Set up environment variables:
Create a `.env` file in the project root with the following content:
```
SECRET_KEY=your-secret-key
DATABASE_URL=mysql://username:password@localhost/agro_management
```

6. Initialize the database:
```bash
flask db init
flask db migrate
flask db upgrade
```

## Running the Application

1. Start the Flask development server:
```bash
python run.py
```

2. Open your web browser and navigate to `http://localhost:5000`

## User Roles and Permissions

### Agrodealer
- Can view and request stock
- Can process sales
- Can upload invoices for approved requests

### Sector Agronomy Officer (SAO)
- Can review and approve stock requests
- Can view transaction history

### Manager Director (MD)
- Can approve stock requests
- Can view financial reports
- Can export financial data
- Can update stock levels

## Database Structure

The application uses the following main tables:
- Users
- Products
- Stock Requests
- Customers
- Transactions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 