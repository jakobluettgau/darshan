import sys
import os
import io
import base64
import argparse
import datetime
if sys.version_info >= (3, 7):
    import importlib.resources as importlib_resources
else:
    import importlib_resources

from typing import Any, Union, Callable

import pandas as pd
from mako.template import Template

import darshan
import darshan.cli
from darshan.experimental.plots import plot_dxt_heatmap

darshan.enable_experimental()


class ReportFigure:
    """
    Stores info for each figure in `ReportData.register_figures`.

    Parameters
    ----------
    section_title : the title of the section the figure belongs to.

    fig_title : the title of the figure.

    fig_func : the function used to generate the figure.

    fig_args : the keyword arguments used for `fig_func`

    fig_description : description of the figure, typically used as the caption.

    fig_width : the width of the figure in pixels.

    """
    def __init__(
        self,
        section_title: str,
        fig_title: str,
        fig_func: Callable,
        fig_args: dict,
        fig_description: str = "",
        fig_width: int = 500,
    ):
        self.section_title = section_title
        self.fig_title = fig_title
        self.fig_func = fig_func
        self.fig_args = fig_args
        self.fig_description = fig_description
        self.fig_width = fig_width
        # temporary handling for DXT disabled cases
        # so special error message can be passed
        # in place of an encoded image
        self.img_str = None
        if self.fig_func:
            self.generate_img()

    @staticmethod
    def get_encoded_fig(mpl_fig: Any):
        """
        Encode a `matplotlib` figure using base64 encoding.

        Parameters
        ----------
        mpl_fig : ``matplotlib.figure`` object.

        Returns
        -------
        encoded_fig : base64 encoded image.

        """
        tmpfile = io.BytesIO()
        mpl_fig.savefig(tmpfile, format="png", dpi=300)
        encoded_fig = base64.b64encode(tmpfile.getvalue()).decode("utf-8")
        return encoded_fig

    def generate_img(self):
        """
        Generate the image using the figure data.
        """
        # generate the matplotlib figure using the figure's
        # function and function arguments
        mpl_fig = self.fig_func(**self.fig_args)
        # encode the matplotlib figure
        encoded = self.get_encoded_fig(mpl_fig=mpl_fig)
        # create the img string
        self.img_str = f"<img src=data:image/png;base64,{encoded} alt={self.fig_title} width={self.fig_width}>"

class ReportData:
    """
    Collects all of the metadata, tables, and figures
    required to generate a Darshan Summary Report.

    Parameters
    ----------
    log_path: path to a darshan log file.

    """
    def __init__(self, log_path: str):
        # store the log path and use it to generate the report
        self.log_path = log_path
        # store the report
        self.report = darshan.DarshanReport(log_path, read_all=True)
        # create the header/footer
        self.get_header()
        self.get_footer()
        # create the metadata and module tables
        self.get_metadata_table()
        self.get_module_table()
        # register the report figures
        self.register_figures()
        # use the figure data to build the report sections
        self.build_sections()
        # collect the CSS stylesheet
        self.get_stylesheet()

    @staticmethod
    def get_full_command(report: darshan.report.DarshanReport) -> str:
        """
        Retrieves the full command line from the report metadata.

        Parameters
        ----------
        report: a ``darshan.DarshanReport``.

        Returns
        -------
        cmd : the full command line used to generate the darshan log.

        """
        # assign the executable from the report metadata
        cmd = report.metadata["exe"]
        if not cmd:
            # if there is no executable
            # label as not available
            cmd = "N/A"
        elif cmd.isdigit():
            # if it can be converted to an
            # integer label it anonymized
            cmd = "Anonymized"
        return cmd

    @staticmethod
    def get_runtime(report: darshan.report.DarshanReport) -> str:
        """
        Calculates the run time from the report metadata.

        Parameters
        ----------
        report: a ``darshan.DarshanReport``.

        Returns
        -------
        runtime : the calculated executable run time.

        """
        # calculate the run time
        runtime_val = float(
            report.metadata["job"]["end_time"] - report.metadata["job"]["start_time"]
        )
        if runtime_val < 1.0:
            # to prevent the displayed run time from being 0.0 seconds
            # label anything under 1 second as less than 1
            runtime = "< 1"
        else:
            runtime = str(runtime_val)
        return runtime

    def get_header(self):
        """
        Builds the header string for the summary report.
        """
        command = self.get_full_command(report=self.report)
        if command in ["Anonymized", "N/A"]:
            app_name = command
        else:
            app_name = os.path.basename(command.split()[0])
        # collect the date from the time stamp
        date = datetime.date.fromtimestamp(self.report.metadata["job"]["start_time"])
        # the header is the application name and the log date
        self.header = f"{app_name} ({date})"

    def get_footer(self):
        """
        Builds the footer string for the summary report.
        """
        lib_ver = darshan.__version__
        self.footer = f"Summary report generated via PyDarshan v{lib_ver}"

    def get_metadata_table(self):
        """
        Builds the metadata table (in html form) for the summary report.
        """
        # assign the metadata dictionary
        job_data = self.report.metadata["job"]
        # build a dictionary with the appropriate metadata
        metadata_dict = {
            "Job ID": job_data["jobid"],
            "User ID": job_data["uid"],
            "# Processes": job_data["nprocs"],
            "Runtime (s)": self.get_runtime(report=self.report),
            "Start Time": datetime.datetime.fromtimestamp(job_data["start_time"]),
            "End Time": datetime.datetime.fromtimestamp(job_data["end_time"]),
            "Command": self.get_full_command(report=self.report),
            "Log Filename": os.path.basename(self.log_path),
            "Runtime Library Version": job_data["metadata"]["lib_ver"],
            "Log Format Version": job_data["log_ver"],
        }
        # convert the dictionary into a dataframe
        metadata_df = pd.DataFrame.from_dict(data=metadata_dict, orient="index")
        # write out the table in html
        self.metadata_table = metadata_df.to_html(header=False, border=0)

    def get_module_table(self):
        """
        Builds the module table (in html form) for the summary report.
        """
        # construct a dictionary containing the module names
        # and their respective data stored in KiB
        module_dict = {}
        for mod in self.report.modules:
            # retrieve the module version and buffer sizes
            mod_version = self.report.modules[mod]["ver"]
            # retrieve the buffer size converted to KiB
            mod_buf_size = self.report.modules[mod]["len"] / 1024
            # create the key/value pairs for the dictionary
            key = f"{mod} (ver={mod_version})"
            val = f"{mod_buf_size:.2f} KiB"
            if self.report.modules[mod]["partial_flag"]:
                val += " (partial data)"
            module_dict[key] = val

        # convert the module dictionary into a dataframe
        module_df = pd.DataFrame.from_dict(data=module_dict, orient="index")
        # write out the table in html
        self.module_table = module_df.to_html(header=False, border=0)

    def get_stylesheet(self):
        """
        Retrieves the locally stored CSS.
        """
        # get the path to the style sheet
        with importlib_resources.path(darshan.cli, "style.css") as path:
            # collect the css entries
            with open(path, "r") as f:
                self.stylesheet = "".join(f.readlines())

    def register_figures(self):
        """
        Collects and registers all figures in the report. This is the
        method users can edit to alter the report contents.

        Examples
        --------
        To add figures to the report, there are a few basic steps:

        1. Make the function used to generate the desired figure
           callable within the scope of this module.
        2. Create an entry in this method that contains all of the required
           information for the figure. This will be described in detail below.
        3. Use the figure information to create a `ReportFigure`.
        4. Add the `ReportFigure` to `ReportData.figures`.

        Step #1 is handled by importing the function from the module it is
        defined in. For step #2, each figure in the report must have the
        following defined:

        * Section title: the desired section for the figure to be placed.
          If the section title is unique to the report, a new section
          will be created for that figure.
        * Figure title: the title of the figure
        * Figure function: the function used to produce the figure. This
          must be callable within the scope of this module (step #1).
        * Figure arguments: the arguments for the figure function

        Some additional details can be provided as well:

        * Figure description: description of the figure used for the caption
        * Figure width: width of the figure in pixels

        To complete steps 2-4, an entry can be added to this method,
        where a typical entry will look like the following:

            # collect all of the info in a dictionary (step #2)
            fig_params = {
                "section_title": "Example Section Title",
                "fig_title": "Example Title",
                "fig_func": example_module.example_function,
                "fig_args": dict(report=self.report),
                "fig_description": "Example Caption",
                "fig_width": 500,
            }
            # feed the dictionary into ReportFigure (step #3)
            example_fig = ReportFigure(**fig_params)
            # add the ReportFigure to ReportData.figures (step #4)
            self.figures.append(example_fig)

        The order of the sections and figures is based on the order in which
        they are placed in `self.figures`. Since the DXT figure(s) are added
        first, they show up at the very top of the figure list.

        """
        self.figures = []

        ############################
        ## Add the DXT heat map(s)
        ############################
        # if either or both modules are present, register their figures
        hmap_description = (
            "Heat map of I/O (in bytes) over time broken down by MPI rank. "
            "Bins are populated based on the number of bytes read/written in "
            "the given time interval. The vertical bar graph sums each time "
            "slice across all ranks to show the total I/O over time, while the "
            "horizontal bar graph sums all I/O events for each rank to "
            "illustrate how the I/O was distributed across ranks."
        )
        if "DXT" in "\t".join(self.report.modules):
            for mod in ["DXT_POSIX", "DXT_MPIIO"]:
                if mod in self.report.modules:
                    dxt_heatmap_fig = ReportFigure(
                        section_title="I/O Operations",
                        fig_title=f"Heat Map: {mod}",
                        fig_func=plot_dxt_heatmap.plot_heatmap,
                        fig_args=dict(report=self.report, mod=mod),
                        fig_description=hmap_description,
                    )
                    self.figures.append(dxt_heatmap_fig)
        else:
            # temporary message to direct users to DXT tracing
            # documentation until DXT tracing is enabled by default
            url = (
                "https://www.mcs.anl.gov/research/projects/darshan/docs/darshan"
                "-runtime.html#_using_the_darshan_extended_tracing_dxt_module"
            )
            temp_message = (
                f"Heat map is not available for this job as DXT was not "
                f"enabled at run time. For details on how to enable DXT visit "
                f"the <a href={url}>Darshan-runtime documentation</a>."
            )
            fig = ReportFigure(
                section_title="I/O Operations",
                fig_title="Heat Map",
                fig_func=None,
                fig_args=None,
                fig_description=temp_message,
            )
            self.figures.append(fig)

    def build_sections(self):
        """
        Uses figure info to generate the unique sections
        and places the figures in their sections.
        """
        self.sections = {}
        for fig in self.figures:
            # if a section title is not already in sections, add
            # the section title and a corresponding empty dictionary
            # to store its figures
            if fig.section_title not in self.sections:
                self.sections[fig.section_title] = {}
            # add the image to its corresponding section
            self.sections[fig.section_title][fig.fig_title] = fig


def setup_parser(parser: argparse.ArgumentParser):
    """
    Configures the command line arguments.

    Parameters
    ----------
    parser : command line argument parser.

    """
    parser.description = "Generates a Darshan Summary Report"

    parser.add_argument(
        "log_path",
        type=str,
        help="Specify path to darshan log.",
    )
    parser.add_argument("--output", type=str, help="Specify output filename.")


def main(args: Union[Any, None] = None):
    """
    Generates a Darshan Summary Report.

    Parameters
    ----------
    args: command line arguments.

    """
    if args is None:
        parser = argparse.ArgumentParser(description="")
        setup_parser(parser)
        args = parser.parse_args()

    log_path = args.log_path

    if args.output is None:
        # if no output is provided, use the log file
        # name to create the output filename
        log_filename = os.path.splitext(os.path.basename(log_path))[0]
        report_filename = f"{log_filename}_report.html"
    else:
        report_filename = args.output

    # collect the report data to feed into the template
    report_data = ReportData(log_path=log_path)

    with importlib_resources.path(darshan.cli, "base.html") as base_path:
        # load a template object using the base template
        template = Template(filename=str(base_path))
        # render the base template
        stream = template.render(report_data=report_data)
        with open(report_filename, "w") as f:
            # print a message so users know where to look for their report
            save_path = os.path.join(os.getcwd(), report_filename)
            print(
                f"Report generated successfully. \n"
                f"Saving report at location: {save_path}"
            )
            # save the rendered html
            f.write(stream)


if __name__ == "__main__":
    main()
