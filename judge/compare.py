import os
import re
import csv
import sys
from glob import glob

def process_result_file(file_path):
    """
    Process a result file and extract valid performance metrics.
    
    Args:
        file_path (str): Path to the result file
        
    Returns:
        tuple: (valid_records, avg_trun, avg_wt, avg_w)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # Try with different encodings if utf-8 fails
        try:
            with open(file_path, 'r', encoding='utf-16') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return 0, 0, 0, 0
    
    # Split the content into records using multiple '-' as separator
    records = re.split(r'-{5,}', content)
    
    valid_records = []
    for record in records:
        record = record.strip()
        if not record:
            continue
        
        # Check if the record is valid (contains "Accepted")
        if "Accepted" in record:
            # Extract Trun, WT, and W values
            trun_match = re.search(r'Trun:\s*([-+]?\d*\.\d+|\d+)', record)
            wt_match = re.search(r'WT:\s*([-+]?\d*\.\d+|\d+)', record)
            w_match = re.search(r'W:\s*([-+]?\d*\.\d+|\d+)', record)
            
            if trun_match and wt_match and w_match:
                trun = float(trun_match.group(1))
                wt = float(wt_match.group(1))
                w = float(w_match.group(1))
                valid_records.append((trun, wt, w))
    
    # Calculate averages
    if valid_records:
        avg_trun = sum(record[0] for record in valid_records) / len(valid_records)
        avg_wt = sum(record[1] for record in valid_records) / len(valid_records)
        avg_w = sum(record[2] for record in valid_records) / len(valid_records)
        return len(valid_records), avg_trun, avg_wt, avg_w
    else:
        return 0, 0, 0, 0

def main(output_file='compare.csv', input_files=None):
    """
    Main function to process result files and output statistics.
    
    Args:
        output_file (str): Path to the output CSV file
        input_files (list): List of input file paths. If None, uses result.txt
    """
    print("Starting program...")
    if input_files is None:
        # If no input files specified, use result.txt in the current directory
        input_files = ['result.txt']
    
    print(f"Processing files: {input_files}")
    results = []
    
    for file_pattern in input_files:
        # Handle wildcards in file patterns
        for file_path in glob(file_pattern):
            file_name = os.path.basename(file_path)
            valid_count, avg_trun, avg_wt, avg_w = process_result_file(file_path)
            
            if valid_count > 0:
                results.append({
                    'file_name': file_name,
                    'valid_records': valid_count,
                    'avg_trun': avg_trun,
                    'avg_wt': avg_wt,
                    'avg_w': avg_w
                })
                print(f"Processed {file_name}: {valid_count} valid records, "
                      f"Avg Trun: {avg_trun:.4f}, Avg WT: {avg_wt:.4f}, Avg W: {avg_w:.4f}")
            else:
                print(f"No valid records found in {file_name}")
    
    # Write results to CSV file
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(['file_name', 'Trun', 'WT', 'W'])
            
            # Write data
            for result in results:
                writer.writerow([
                    result['file_name'],
                    f"{result['avg_trun']:.4f}",
                    f"{result['avg_wt']:.4f}",
                    f"{result['avg_w']:.4f}"
                ])
        
        print(f"\nResults written to {output_file}")
    except Exception as e:
        print(f"Error writing to {output_file}: {e}")

if __name__ == "__main__":
    # Write debug info to a file
    with open('debug_output.txt', 'w') as debug_file:
        debug_file.write("Debug output from compare.py\n")
        debug_file.write(f"Arguments: {sys.argv}\n")
        
        try:
            # Parse command line arguments
            if len(sys.argv) > 1:
                # If arguments are provided, use them as input files
                debug_file.write(f"Using input files: {sys.argv[1:]}\n")
                main(input_files=sys.argv[1:])
            else:
                # Otherwise, use default (result.txt)
                debug_file.write("Using default input file: result.txt\n")
                main()
        except Exception as e:
            debug_file.write(f"Error: {e}\n")
            import traceback
            debug_file.write(traceback.format_exc())
