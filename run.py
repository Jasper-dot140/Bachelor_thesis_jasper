# cspell:disable
#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path
import time
import sys
import threading
import signal
import re  # ADD THIS LINE
from datetime import datetime
import argparse
import tempfile


def tprint(*args, **kwargs):
    """Print with timestamp"""
    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S.%f")[:-3]  # Include milliseconds
    
    # Convert args to strings and apply color formatting
    colored_args = []
    for arg in args:
        arg_str = str(arg)
        # Replace checkmarks with green checkmarks
        arg_str = arg_str.replace('✓', '\033[92m✓\033[0m')
        # Replace X marks with red X marks
        arg_str = arg_str.replace('✗', '\033[91m✗\033[0m')
        # Replace warning symbols with yellow warning symbols
        arg_str = arg_str.replace('⚠', '\033[93m⚠\033[0m')
        # Replace skip symbols with blue skip symbols
        arg_str = arg_str.replace('⏭', '\033[94m⏭\033[0m')
        colored_args.append(arg_str)
    
    print(f"[{timestamp}]", *colored_args, **kwargs)

class CompilationSpinner:
    def __init__(self):
        self.spinning = False
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.thread = None
        
    def start(self, message="Compiling"):
        self.spinning = True
        self.thread = threading.Thread(target=self._spin, args=(message,))
        self.thread.start()
        
    def stop(self):
        self.spinning = False
        if self.thread:
            self.thread.join()
        # Clear the line
        print('\r' + ' ' * 80 + '\r', end='', flush=True)
        
    def _spin(self, message):
        idx = 0
        start_time = time.time()
        while self.spinning:
            elapsed = time.time() - start_time
            minutes, seconds = divmod(int(elapsed), 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            
            spinner_char = self.spinner_chars[idx % len(self.spinner_chars)]
            print(f'\r{spinner_char} {message}... [{time_str}] (Press Ctrl+C to cancel)', end='', flush=True)
            time.sleep(0.1)
            idx += 1

# Add this after the CompilationSpinner class and before signal_handler

def count_equations_detailed():
    """Count equations with detailed breakdown"""
    try:
        import re
        
        equation_types = {
            'equation': 0,
            'equation*': 0,
            'align': 0,
            'align*': 0,
            'gather': 0,
            'gather*': 0,
            'multline': 0,
            'multline*': 0
        }
        
        tex_files = list(Path('.').rglob('*.tex'))
        
        for tex_file in tex_files:
            try:
                with open(tex_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                # Use more specific patterns to avoid double counting
                for env_type in equation_types.keys():
                    if '*' in env_type:
                        # For starred environments, match exactly
                        pattern = f'\\\\begin{{{re.escape(env_type)}}}'
                    else:
                        # For non-starred environments, use negative lookahead to exclude starred versions
                        base_type = env_type
                        pattern = f'\\\\begin{{{base_type}}}(?!\\*)'
                    
                    equation_types[env_type] += len(re.findall(pattern, content))
                    
            except Exception:
                continue
        
        total = sum(equation_types.values())
        
        # Print breakdown
        tprint("📊 Equation breakdown:")
        for env_type, count in equation_types.items():
            if count > 0:
                tprint(f"   {env_type}: {count}")
        
        return total
        
    except Exception:
        return 0

def parse_warnings(log_content):
    """Parse LaTeX warnings from log content (excluding info messages and boxes)"""
    warnings = []
    auxiliary_info = []
    
    warning_patterns = [
        # LaTeX warnings (exclude Font Info)
        r'LaTeX Warning: (.+)',
        r'Package \w+ Warning: (.+)',
        # Bibliography warnings
        r'Warning--(.+)',
        # Missing references
        r'LaTeX Warning: Reference `(.+)\' on page \d+ undefined',
        r'LaTeX Warning: Citation `(.+)\' on page \d+ undefined',
        # Package-specific warnings (excluding info)
        r'Package hyperref Warning: (.+)',
        r'Package babel Warning: (.+)',
        r'Package inputenc Warning: (.+)',
        r'Package fancyhdr Warning: (.+)',
        r'Package geometry Warning: (.+)',
    ]
    
    # Auxiliary information patterns (overfull/underfull boxes)
    auxiliary_patterns = [
        r'(Overfull \\hbox.+)',
        r'(Underfull \\hbox.+)',
        r'(Overfull \\vbox.+)',
        r'(Underfull \\vbox.+)',
    ]
    
    # Patterns to EXCLUDE (info messages)
    exclude_patterns = [
        r'LaTeX Font Info:',
        r'Package .* Info:',
        r'File: .* Graphic file',
        r'Document Class:',
        r'\\openout\d+',
        r'For additional information on amsmath',
    ]
    
    lines = log_content.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        
        # Skip if it matches exclude patterns
        should_exclude = any(re.search(exclude_pattern, line, re.IGNORECASE) 
                           for exclude_pattern in exclude_patterns)
        if should_exclude:
            continue
        
        # Check for auxiliary info patterns first
        is_auxiliary = False
        for pattern in auxiliary_patterns:
            matches = re.finditer(pattern, line, re.IGNORECASE)
            for match in matches:
                aux_text = match.group(1) if match.groups() else match.group(0)
                auxiliary_info.append({
                    'line': line_num,
                    'text': aux_text.strip(),
                    'full_line': line
                })
                is_auxiliary = True
        
        # If not auxiliary info, check for warning patterns
        if not is_auxiliary:
            for pattern in warning_patterns:
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for match in matches:
                    warning_text = match.group(1) if match.groups() else match.group(0)
                    warnings.append({
                        'line': line_num,
                        'text': warning_text.strip(),
                        'full_line': line
                    })
    
    return warnings, auxiliary_info

def count_and_display_warnings():
    """Count and display warnings from LaTeX log"""
    try:
        output_dir = Path("output")
        log_file = output_dir / "main.log"
        if not log_file.exists():
            tprint("⚠ Log file not found - cannot analyze warnings")
            return 0, 0
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            log_content = f.read()
        
        warnings, auxiliary_info = parse_warnings(log_content)
        
        # Display warnings
        if warnings:
            tprint(f"⚠ Found {len(warnings)} warnings:")
            
            # Group warnings by type
            warning_types = {}
            for warning in warnings:
                # Extract warning type
                if 'undefined' in warning['text'].lower():
                    warning_type = 'Undefined references'
                elif 'citation' in warning['text'].lower():
                    warning_type = 'Citation issues'
                elif 'hyperref' in warning['full_line'].lower():
                    warning_type = 'Hyperref warnings'
                elif 'package' in warning['full_line'].lower():
                    warning_type = 'Package warnings'
                else:
                    warning_type = 'General warnings'
                
                if warning_type not in warning_types:
                    warning_types[warning_type] = []
                warning_types[warning_type].append(warning)
            
            # Display warning summary by type
            for warning_type, type_warnings in warning_types.items():
                tprint(f"   {warning_type}: {len(type_warnings)}")
            
            # Display first few warnings of each type
            if len(warnings) > 0:
                tprint("📋 Warning details (first 2 per type):")
                for warning_type, type_warnings in warning_types.items():
                    tprint(f"\n   {warning_type}:")
                    for i, warning in enumerate(type_warnings[:2]):  # Show first 2
                        tprint(f"     • {warning['text']}")
                    if len(type_warnings) > 2:
                        tprint(f"     ... and {len(type_warnings) - 2} more")
        else:
            tprint("✓ No warnings found!")
        
        # Display auxiliary information (boxes)
        if auxiliary_info:
            tprint(f"ℹ️  Found {len(auxiliary_info)} layout notifications:")
            
            # Group auxiliary info by type
            aux_types = {}
            for aux in auxiliary_info:
                if 'Overfull' in aux['text']:
                    aux_type = 'Overfull boxes'
                elif 'Underfull' in aux['text']:
                    aux_type = 'Underfull boxes'
                else:
                    aux_type = 'Other layout'
                
                if aux_type not in aux_types:
                    aux_types[aux_type] = []
                aux_types[aux_type].append(aux)
            
            # Display auxiliary summary by type
            for aux_type, type_aux in aux_types.items():
                tprint(f"   {aux_type}: {len(type_aux)}")
                
            # Optionally show first few auxiliary details
            if len(auxiliary_info) <= 5:  # Only show details if not too many
                tprint("\n📐 Layout details:")
                for aux_type, type_aux in aux_types.items():
                    for i, aux in enumerate(type_aux[:2]):  # Show first 2
                        tprint(f"     • {aux['text'][:80]}...")  # Truncate long lines
        else:
            tprint("\n✓ No layout issues found!")
        
        return len(warnings), len(auxiliary_info)
        
    except Exception as e:
        tprint(f"⚠ Error analyzing warnings: {e}")
        return 0, 0

# Global variables for process management
current_process = None
spinner = None

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global current_process, spinner
    
    print('\n')  # New line after Ctrl+C
    tprint("⚠ Received interrupt signal (Ctrl+C)")
    
    if spinner:
        spinner.stop()
    
    if current_process:
        tprint("🔄 Terminating compilation process...")
        try:
            current_process.terminate()
            # Wait a bit for graceful termination
            current_process.wait(timeout=5)
            tprint("✓ Process terminated gracefully")
        except subprocess.TimeoutExpired:
            tprint("⚠ Process didn't terminate gracefully, forcing kill...")
            current_process.kill()
            current_process.wait()
            tprint("✓ Process killed")
        except Exception as e:
            tprint(f"⚠ Error terminating process: {e}")
    
    tprint("✗ Compilation cancelled by user")
    sys.exit(130)  # Standard exit code for Ctrl+C

def compile_main_tex():
    """Compile main.tex using latexmk"""
    global current_process, spinner
    
    try:
        # Check if main.tex exists
        main_tex = Path("main.tex")
        if not main_tex.exists():
            tprint("✗ main.tex not found in current directory")
            return False
        
        # Create output directory
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        tprint("Starting compilation of main.tex...")
        tprint("💡 Press Ctrl+C to cancel compilation at any time")
        
        # Start spinner
        spinner = CompilationSpinner()
        spinner.start("Compiling main.tex")
        
        try:
            # Run latexmk with Popen for better process control
            current_process = subprocess.Popen([
                'latexmk',
                '-synctex=1',
                '-interaction=nonstopmode',
                '-file-line-error',
                '-halt-on-error',
                '-shell-escape',
                '-lualatex',
                '-recorder',      # Always track dependencies
                '-use-make',       # Always use smart recompilation
                f'-outdir={output_dir.absolute()}',
                'main.tex'
            ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for process to complete
            stdout, stderr = current_process.communicate(timeout=6000)  # 100 minute timeout
            
            # Create a result-like object
            class Result:
                def __init__(self, returncode, stdout, stderr):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr
            
            result = Result(current_process.returncode, stdout, stderr)
            
        finally:
            # Stop spinner
            if spinner:
                spinner.stop()
            current_process = None
        
        if result.returncode == 0:
            tprint("✓ Successfully compiled main.tex")
            
            # Check if PDF was created
            pdf_path = output_dir / "main.pdf"
            if pdf_path.exists():
                tprint(f"✓ PDF created: {pdf_path}")
                return True
            else:
                tprint("⚠ PDF file not found in output directory")
                return True  # Still consider it successful if latexmk succeeded
        else:
            tprint("✗ Failed to compile main.tex")
            if result.stderr:
                tprint("Error output:")
                print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        if current_process:
            current_process.kill()
        tprint("✗ Timeout compiling main.tex")
        return False
    except KeyboardInterrupt:
        # This shouldn't happen due to signal handler, but just in case
        tprint("✗ Compilation interrupted")
        return False
    except Exception as e:
        tprint(f"✗ Exception compiling main.tex: {str(e)}")
        return False

def count_figures_and_tables():
    """Count figures, tables, plots and their sub-versions with detailed breakdown"""
    try:
        import re
        
        counts = {
            'figures_with_subfigures': 0,
            'figures_without_subfigures': 0,
            'total_subfigures': 0,
            'tables_with_subtables': 0,
            'tables_without_subtables': 0,
            'total_subtables': 0,
            'plots_with_subplots': 0,      # NEW: Custom plot environment
            'plots_without_subplots': 0,   # NEW: Custom plot environment
            'total_subplots': 0,           # NEW: Count of subplot environments
            'tikzpictures_with_plots': 0,
            'tikzpictures_without_plots': 0,
            'pgfplots_with_subplots': 0,
            'pgfplots_without_subplots': 0,
            'total_addplots': 0,
            'standalone_graphics': 0,
        }
        
        tex_files = list(Path('.').rglob('*.tex'))
        
        for tex_file in tex_files:
            try:
                with open(tex_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # === FIGURES ANALYSIS ===
                # Regular figures
                figure_pattern = r'\\begin\{figure\}(.*?)\\end\{figure\}'
                figure_matches = re.findall(figure_pattern, content, re.DOTALL)
                for figure_content in figure_matches:
                    subfigure_count = len(re.findall(r'\\begin\{subfigure\}', figure_content))
                    if subfigure_count > 0:
                        counts['figures_with_subfigures'] += 1
                        counts['total_subfigures'] += subfigure_count
                    else:
                        counts['figures_without_subfigures'] += 1
                
                # Starred figures
                figure_star_pattern = r'\\begin\{figure\*\}(.*?)\\end\{figure\*\}'
                figure_star_matches = re.findall(figure_star_pattern, content, re.DOTALL)
                for figure_content in figure_star_matches:
                    subfigure_count = len(re.findall(r'\\begin\{subfigure\}', figure_content))
                    if subfigure_count > 0:
                        counts['figures_with_subfigures'] += 1
                        counts['total_subfigures'] += subfigure_count
                    else:
                        counts['figures_without_subfigures'] += 1
                
                # === TABLES ANALYSIS ===
                # Regular tables
                table_pattern = r'\\begin\{table\}(.*?)\\end\{table\}'
                table_matches = re.findall(table_pattern, content, re.DOTALL)
                for table_content in table_matches:
                    subtable_count = len(re.findall(r'\\begin\{subtable\}', table_content))
                    if subtable_count > 0:
                        counts['tables_with_subtables'] += 1
                        counts['total_subtables'] += subtable_count
                    else:
                        counts['tables_without_subtables'] += 1
                
                # Starred tables
                table_star_pattern = r'\\begin\{table\*\}(.*?)\\end\{table\*\}'
                table_star_matches = re.findall(table_star_pattern, content, re.DOTALL)
                for table_content in table_star_matches:
                    subtable_count = len(re.findall(r'\\begin\{subtable\}', table_content))
                    if subtable_count > 0:
                        counts['tables_with_subtables'] += 1
                        counts['total_subtables'] += subtable_count
                    else:
                        counts['tables_without_subtables'] += 1
                
                # === CUSTOM PLOT ENVIRONMENTS ANALYSIS ===
                # Your custom plot environment
                plot_pattern = r'\\begin\{plot\}(.*?)\\end\{plot\}'
                plot_matches = re.findall(plot_pattern, content, re.DOTALL)
                for plot_content in plot_matches:
                    subplot_count = len(re.findall(r'\\begin\{subplot\}', plot_content))
                    if subplot_count > 0:
                        counts['plots_with_subplots'] += 1
                        counts['total_subplots'] += subplot_count
                    else:
                        counts['plots_without_subplots'] += 1
                
                # === TIKZ/PGFPLOTS ANALYSIS ===
                # TikZ pictures
                tikz_pattern = r'\\begin\{tikzpicture\}(.*?)\\end\{tikzpicture\}'
                tikz_matches = re.findall(tikz_pattern, content, re.DOTALL)
                for tikz_content in tikz_matches:
                    plot_count = len(re.findall(r'\\addplot|\\plot(?!s)', tikz_content))
                    if plot_count > 0:
                        counts['tikzpictures_with_plots'] += 1
                        counts['total_addplots'] += plot_count
                    else:
                        counts['tikzpictures_without_plots'] += 1
                
                # PGFPlots (axis environments)
                axis_pattern = r'\\begin\{axis\}(.*?)\\end\{axis\}'
                axis_matches = re.findall(axis_pattern, content, re.DOTALL)
                for axis_content in axis_matches:
                    addplot_count = len(re.findall(r'\\addplot', axis_content))
                    if addplot_count > 0:
                        counts['pgfplots_with_subplots'] += 1
                        counts['total_addplots'] += addplot_count
                    else:
                        counts['pgfplots_without_subplots'] += 1
                
                # Standalone graphics (not in figure/table environments)
                all_includegraphics = len(re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}', content))
                counts['standalone_graphics'] += all_includegraphics
                    
            except Exception:
                continue
        
        # Calculate totals
        total_figures = counts['figures_with_subfigures'] + counts['figures_without_subfigures']
        total_tables = counts['tables_with_subtables'] + counts['tables_without_subtables']
        total_custom_plots = counts['plots_with_subplots'] + counts['plots_without_subplots']  # NEW
        total_tikz_pgf_plots = counts['tikzpictures_with_plots'] + counts['pgfplots_with_subplots']
        total_plot_containers = (counts['tikzpictures_with_plots'] + counts['tikzpictures_without_plots'] + 
                               counts['pgfplots_with_subplots'] + counts['pgfplots_without_subplots'] +
                               total_custom_plots)  # Include custom plots in total
        
        # Print breakdown
        tprint("📊 Figures & Tables breakdown:")
        
        if total_figures > 0:
            if counts['figures_with_subfigures'] > 0:
                tprint(f"   📊 {counts['figures_with_subfigures']} figures containing {counts['total_subfigures']} subfigures")
            if counts['figures_without_subfigures'] > 0:
                tprint(f"   📄 {counts['figures_without_subfigures']} standalone figures")
            tprint(f"   → Total figures: {total_figures}")
            
        if total_tables > 0:
            if counts['tables_with_subtables'] > 0:
                tprint(f"   📊 {counts['tables_with_subtables']} tables containing {counts['total_subtables']} subtables")
            if counts['tables_without_subtables'] > 0:
                tprint(f"   📋 {counts['tables_without_subtables']} standalone tables")
            tprint(f"   → Total tables: {total_tables}")
        
        # NEW: Custom plot environments
        if total_custom_plots > 0:
            if counts['plots_with_subplots'] > 0:
                tprint(f"   📈 {counts['plots_with_subplots']} plots containing {counts['total_subplots']} subplots")
            if counts['plots_without_subplots'] > 0:
                tprint(f"   📊 {counts['plots_without_subplots']} standalone plots")
            tprint(f"   → Total custom plots: {total_custom_plots}")
        
        # TikZ/PGFPlots
        if counts['tikzpictures_with_plots'] > 0 or counts['pgfplots_with_subplots'] > 0:
            if counts['tikzpictures_with_plots'] > 0:
                tprint(f"   🎨 {counts['tikzpictures_with_plots']} TikZ pictures with plot commands")
            if counts['pgfplots_with_subplots'] > 0:
                tprint(f"   📊 {counts['pgfplots_with_subplots']} PGFPlots containing {counts['total_addplots']} \\addplot commands")
            
        if counts['tikzpictures_without_plots'] > 0 or counts['pgfplots_without_subplots'] > 0:
            if counts['tikzpictures_without_plots'] > 0:
                tprint(f"   🎨 {counts['tikzpictures_without_plots']} TikZ pictures (diagrams)")
            if counts['pgfplots_without_subplots'] > 0:
                tprint(f"   📊 {counts['pgfplots_without_subplots']} empty PGFPlots")
                
        if total_plot_containers > 0:
            tprint(f"   → Total plot containers: {total_plot_containers}")
            
        if counts['standalone_graphics'] > 0:
            tprint(f"   🖼️  {counts['standalone_graphics']} graphics commands (\\includegraphics)")
        
        # Return summary counts
        return {
            'figures': total_figures,
            'figures_with_subfigures': counts['figures_with_subfigures'],
            'total_subfigures': counts['total_subfigures'],
            'tables': total_tables,
            'tables_with_subtables': counts['tables_with_subtables'],
            'total_subtables': counts['total_subtables'],
            'custom_plots': total_custom_plots,                    # NEW
            'plots_with_subplots': counts['plots_with_subplots'],  # NEW
            'total_subplots': counts['total_subplots'],            # NEW
            'plot_containers': total_plot_containers,
            'tikz_pgf_plots': total_tikz_pgf_plots,
            'total_plot_commands': counts['total_addplots'],
            'graphics': counts['standalone_graphics']
        }
        
    except Exception as e:
        tprint(f"⚠ Error in figure counting: {e}")
        return {
            'figures': 0,
            'figures_with_subfigures': 0,
            'total_subfigures': 0,
            'tables': 0,
            'tables_with_subtables': 0,
            'total_subtables': 0,
            'custom_plots': 0,
            'plots_with_subplots': 0,
            'total_subplots': 0,
            'plot_containers': 0,
            'tikz_pgf_plots': 0,
            'total_plot_commands': 0,
            'graphics': 0
        }

def convert_to_pdfa(quality="medium"):
    """
    Convert PDF to PDF/A-3b format using Ghostscript.
    Attempts to preserve all types of hyperlinks and annotations (e.g., URLs, hyperref, cleveref).
    Quality: 'low', 'medium', or 'high' controls image downsampling resolution.
    """
    import subprocess
    from pathlib import Path

    input_pdf = Path("output/main.pdf")
    if not input_pdf.exists():
        tprint("✗ Input PDF not found: output/main.pdf")
        return False

    output_file = "thesis_pdfa3b.pdf"
    original_size = input_pdf.stat().st_size / (1024*1024)
    tprint(f"🔄 Starting PDF/A-3b conversion (input: {original_size:.2f} MB)")

    temp_pdf = str(input_pdf)

    icc_profile_path = "/usr/share/color/icc/colord/AdobeRGB1998.icc"
    pdfa_def_path = "/usr/share/ghostscript/10.03.1/lib/PDFA_def.ps"

    gs_cmd = [
        "gs",
        "-dPDFA=3",
        "-dBATCH",
        "-dNOPAUSE",
        "-dUseCIEColor",
        "-sProcessColorModel=DeviceRGB",
        "-sDEVICE=pdfwrite",
        "-dPDFACompatibilityPolicy=1",
        "-dCompatibilityLevel=1.7",
        "-dPreserveAnnots=true",
        "-dEmbedAllFonts=true",
        "-dSubsetFonts=true",
        "-dDetectDuplicateImages=true",
        "-dRemoveUnusedResources=true",
        "-dColorImageDownsampleType=/Bicubic",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dMonoImageDownsampleType=/Subsample",
        # downsampling options...

        f"-sOutputFile={output_file}",

        pdfa_def_path,   # PDFA_def.ps loaded before input pdf

        "-c", "/PreserveAnnotTypes [/Link /Text /Underline /Highlight /Squiggly /StrikeOut /FreeText] def",

        "-f", temp_pdf
    ]


    try:
        subprocess.run(gs_cmd, check=True, capture_output=True, text=True)

        if Path(output_file).exists():
            final_size = Path(output_file).stat().st_size / (1024*1024)
            size_ratio = final_size / original_size

            tprint(f"✓ Conversion complete: {original_size:.2f} MB → {final_size:.2f} MB ({size_ratio:.3f}x)")
            if size_ratio > 1.2:
                tprint("⚠️  File size increased more than expected")
            else:
                tprint("✓ File size preserved successfully")

            tprint(f"📄 PDF/A-3b file: {output_file}")
            tprint(f"💡 Validate: verapdf --flavour 3b {output_file}")
            return True
        else:
            tprint("✗ Output file not created")
            return False

    except subprocess.CalledProcessError as e:
        tprint(f"✗ Conversion failed: {e}")
        return False

    except FileNotFoundError as e:
        tprint(f"✗ Tool not found: {e}")
        return False

def main():     
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='LaTeX Main Document Compiler')
    parser.add_argument('--pdfa', action='store_true', 
                       help='Convert to PDF/A-1b after successful compilation')
    
    args = parser.parse_args()
    
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    tprint("LaTeX Main Document Compiler")
    tprint("=" * 40)
    
    start_time = time.time()
    success = compile_main_tex()
    end_time = time.time()
    
    total_time = end_time - start_time
    
    # Count equations and figures/tables after successful compilation
    if success:
        tprint("📊 Analyzing document structure...")
        equation_count = count_equations_detailed()
        figure_counts = count_figures_and_tables()  # ADD THIS LINE
    else:
        equation_count = 0
        figure_counts = count_figures_and_tables()  # Count even if compilation failed
    
    # Count warnings and auxiliary info (unpack the tuple)
    tprint("⚠ Analyzing compilation output...")
    warning_count, aux_count = count_and_display_warnings()
    
    tprint("=" * 40)
    tprint("COMPILATION SUMMARY")
    tprint("=" * 40)
    tprint(f"File: main.tex")
    tprint(f"Total time: {total_time:.2f} seconds")
    
    if success and equation_count > 0:
        tprint(f"Total equations: {equation_count}")
    
    # IMPROVED FIGURE/TABLE/PLOT COUNTS TO SUMMARY
    if figure_counts['figures'] > 0:
        tprint(f"Total figures: {figure_counts['figures']}")
        if figure_counts['figures_with_subfigures'] > 0:
            tprint(f"  • Figures with subfigures: {figure_counts['figures_with_subfigures']} ({figure_counts['total_subfigures']} subfigures)")
        if figure_counts['figures'] - figure_counts['figures_with_subfigures'] > 0:
            standalone_figures = figure_counts['figures'] - figure_counts['figures_with_subfigures']
            tprint(f"  • Standalone figures: {standalone_figures}")

    if figure_counts['tables'] > 0:
        tprint(f"Total tables: {figure_counts['tables']}")
        if figure_counts['tables_with_subtables'] > 0:
            tprint(f"  • Tables with subtables: {figure_counts['tables_with_subtables']} ({figure_counts['total_subtables']} subtables)")
        if figure_counts['tables'] - figure_counts['tables_with_subtables'] > 0:
            standalone_tables = figure_counts['tables'] - figure_counts['tables_with_subtables']
            tprint(f"  • Standalone tables: {standalone_tables}")

    if figure_counts['custom_plots'] > 0:
        tprint(f"Total custom plots: {figure_counts['custom_plots']}")
        if figure_counts['plots_with_subplots'] > 0:
            tprint(f"  • Plots with subplots: {figure_counts['plots_with_subplots']} ({figure_counts['total_subplots']} subplots)")
        if figure_counts['custom_plots'] - figure_counts['plots_with_subplots'] > 0:
            standalone_plots = figure_counts['custom_plots'] - figure_counts['plots_with_subplots']
            tprint(f"  • Standalone plots: {standalone_plots}")

    if figure_counts['plot_containers'] > 0:
        tprint(f"Total plot containers: {figure_counts['plot_containers']}")
        if figure_counts['tikz_pgf_plots'] > 0:
            tprint(f"  • TikZ/PGF plots: {figure_counts['tikz_pgf_plots']}")
    
    if figure_counts['graphics'] > 0:
        tprint(f"Total graphics commands: {figure_counts['graphics']}")
    
    tprint(f"Warnings: {warning_count}")
    tprint(f"Layout notifications: {aux_count}")
    
    if success:
        if warning_count > 0:
            tprint("✓ Compilation completed successfully (with warnings)")
        elif aux_count > 0:
            tprint("✓ Compilation completed successfully (with layout notifications)")
        else:
            tprint("✓ Compilation completed successfully!")
            
        if args.pdfa:
            tprint("Pre-Converting to PDF/A...")
            convert_sucess = convert_to_pdfa()
            
            if convert_sucess:
                tprint("✓ PDF/A pre-conversion completed successfully!")
                tprint("📄 For PDF/A-1/2/3a/b/u conversion -> https://www.pdfforge.org/online/en/pdf-to-pdfa")
            else:
                tprint("✗ PDF/A pre-conversion failed!")
        sys.exit(0)
    else:
        tprint("✗ Compilation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()