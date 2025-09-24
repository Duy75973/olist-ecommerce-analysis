# src/etl/main_etl.py

import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import logging
import re

# --- Cấu hình logging ---
# Thiết lập để log ra file và console, giúp dễ dàng debug
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("etl.log"),
        logging.StreamHandler()
    ]
)

# --- Tải biến môi trường ---
load_dotenv()
logging.info("Đã tải các biến môi trường.")

# --- Lấy thông tin kết nối từ .env ---
db_user = os.getenv('MYSQL_USER')
db_password = os.getenv('MYSQL_PASSWORD')
db_host = os.getenv('MYSQL_HOST')
db_port = os.getenv('MYSQL_PORT')
db_name = os.getenv('MYSQL_DATABASE')

# --- Đường dẫn và ánh xạ file ---
DATA_PATH = 'data/raw/'

# Dictionary ánh xạ tên file CSV tới tên bảng SQL
# Sử dụng regex để bỏ phần "olist_" và "_dataset.csv"
def get_table_name_from_filename(filename):
    """Chuyển tên file CSV thành tên bảng SQL."""
    # Ví dụ: 'olist_customers_dataset.csv' -> 'customers'
    match = re.search(r'olist_(.*?)_dataset\.csv', filename)
    if match:
        # Nếu là 'order_payments', giữ nguyên, không đổi thành 'payment'
        if 'order_payments' in filename:
            return 'order_payments'
        # Trường hợp chung
        return match.group(1).replace('_', '') + 's' if not match.group(1).endswith('s') else match.group(1)
    # Xử lý các trường hợp đặc biệt nếu cần
    if 'product_category_name_translation.csv' in filename:
        return 'product_category_name_translation'
    return None

def find_datetime_columns(df):
    """Tìm các cột có tên chứa 'date' hoặc 'timestamp' để chuyển đổi."""
    return [col for col in df.columns if 'date' in col or 'timestamp' in col]

def run_etl():
    """
    Hàm chính thực thi quy trình ETL.
    1. Tạo kết nối tới DB.
    2. Lặp qua các file CSV trong thư mục data/raw.
    3. Với mỗi file, đọc dữ liệu, xử lý (chuyển đổi ngày tháng) và nạp vào bảng tương ứng.
    """
    try:
        connection_string = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        engine = create_engine(connection_string)
        logging.info(f"Kết nối tới database '{db_name}' thành công.")
    except Exception as e:
        logging.error(f"Lỗi kết nối database: {e}")
        return

    csv_files = [f for f in os.listdir(DATA_PATH) if f.endswith('.csv')]
    
    # Sắp xếp để nạp các bảng "cha" trước (customers, sellers, products)
    # Tránh lỗi khóa ngoại
    load_order = [
        'olist_customers_dataset.csv',
        'olist_sellers_dataset.csv',
        'olist_products_dataset.csv',
        'olist_orders_dataset.csv',
        'olist_order_items_dataset.csv',
        'olist_order_payments_dataset.csv',
        'olist_order_reviews_dataset.csv',
    ]
    
    # Lọc ra các file có trong load_order
    files_to_load = [f for f in load_order if f in csv_files]

    for csv_file in files_to_load:
        file_path = os.path.join(DATA_PATH, csv_file)
        # Bỏ qua bảng dịch thuật, chúng ta có thể xử lý sau nếu cần
        if 'translation' in csv_file:
            continue
            
        # Ánh xạ tên file sang tên bảng
        table_name_map = {
            'olist_customers_dataset.csv': 'customers',
            'olist_sellers_dataset.csv': 'sellers',
            'olist_products_dataset.csv': 'products',
            'olist_orders_dataset.csv': 'orders',
            'olist_order_items_dataset.csv': 'order_items',
            'olist_order_payments_dataset.csv': 'order_payments',
            'olist_order_reviews_dataset.csv': 'order_reviews'
        }
        table_name = table_name_map.get(csv_file)
        
        if not table_name:
            logging.warning(f"Bỏ qua file {csv_file} vì không có trong ánh xạ.")
            continue

        try:
            logging.info(f"===== Bắt đầu xử lý file: {csv_file} cho bảng: {table_name} =====")
            
            # 1. EXTRACT
            df = pd.read_csv(file_path)
            logging.info(f"Đọc {len(df)} dòng từ {csv_file}.")

            # 2. TRANSFORM
            # Tìm và chuyển đổi các cột ngày tháng sang định dạng datetime
            datetime_cols = find_datetime_columns(df)
            if datetime_cols:
                for col in datetime_cols:
                    df[col] = pd.to_datetime(df[col], errors='coerce')
                logging.info(f"Đã chuyển đổi các cột datetime: {datetime_cols}")

            # Đảm bảo tên cột trong DataFrame khớp với tên cột trong DB
            # (Dataset này khá sạch nên tên cột đã khớp)
            
            # 3. LOAD
            logging.info(f"Bắt đầu nạp dữ liệu vào bảng '{table_name}'...")
            df.to_sql(
                name=table_name,
                con=engine,
                if_exists='append', # 'append': thêm dữ liệu vào bảng đã có
                index=False,      # Không ghi cột index của DataFrame vào bảng
                chunksize=1000    # Ghi theo từng chunk để tối ưu bộ nhớ
            )
            logging.info(f"Nạp dữ liệu vào bảng '{table_name}' thành công.")

        except Exception as e:
            logging.error(f"Lỗi khi xử lý file {csv_file}: {e}")
            
    logging.info("===== QUY TRÌNH ETL HOÀN TẤT =====")


if __name__ == '__main__':
    run_etl()