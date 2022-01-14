=======
Byroapi
=======

.. image:: https://img.shields.io/lgtm/grade/python/g/calcite/byroapi.svg?logo=lgtm&logoWidth=18
        :target: https://lgtm.com/projects/g/calcite/byroapi/context:python
        :alt: Language grade: Python

REST API service for filling in and (visually) signing PDF documents.

The administrator provides form templates (PDF documents with blank fields) and
configuration (YAML) describing fields that shall be filled on each PDF document.

The user then POSTs JSON request to the REST API endpoint. The JSON contains
template id and values for the fields defined in the configuration of the
particular template.
The service uses the data in the JSON to write over a template PDF with the data
(text fields or images) and either returns API response with the filled PDF
document, or can send this document as email attachment to a specified address.

Features and limitations
------------------------

* Can add strings over any PDF (doesn't require PDF form fields)
* But, also doesn't yet support PDF form fields ;)
* Can add images with transparent mask (=signatures)
* Supports multi-page documents
* Does not yet support real cryptographic signatures.

Installation
-------------

.. code-block:: console

    $ pip install byroapi

Configuration
-------------

For the usual operation, byroapi requires following:

* configuration file (YAML) - contains entire configuration including template
  definitions
* template files - for each supported PDF form, a "blank" template file is
  required on which the field contents and signatures are overlaid. These
  template files may be multiple for the same form - e.g. bianco signed forms
  for each user, differentiated by filename.
* other assets - image files, additional fonts etc.

Template files and other assets can be stored in any path referenced in the
configuration file.

Configuration file
++++++++++++++++++

Byroapi uses `Onacol`_ configuration, so any configuration parameter described
below can be configured either in the YAML file or through CLI option
or environment variable.

This documentation only describes the YAML configuration method.

To create a configuration file template, use following command::

    $ byroapi --get-config-template your_config.yaml

Typical example configuration with some template looks as follows:

.. code-block:: yaml

    general:
      log_level: INFO  # Logging level [DEBUG, INFO, WARNING, ERROR, CRITICAL]

    templating:  # This section contains all configuration regarding PDF processing
      fonts:  # List of additional TTF fonts to be used in PDF processing
      - name: Arial
        path: fonts/arial.ttf

      templates:  # List of defined templates
        - id:  MyForm
          template:    # Template source
            path:  templates/myform_files
            path_value_substitution:    #
              value: user_id
              pattern: 'myform_{0}_signed.pdf'
          field_defaults: # Default settings for each form field element
            string:
              custom:
                - property: Font
                  values: [ "Arial", 12 ]
          fields: # PDF form field definitions

            - name: date_from
              coords:
                x: 42
                y: 174.5
              type: string

            - name: date_to
              coords:
                x: 75
                y: 174.5
              type: string

            - name: date_approved
              coords:
                x: 57
                y: 132.25
              type: string

            - name: sign_approver
              default: signature2.png
              coords:
                x: 143
                y: 87
              height: 25
              type: image


    email:  # Configuration for email (can be used for sending processed PDF forms)
      smpt:  # SMTP settings as defined in YagMail: https://github.com/kootenpv/yagmail/blob/f24af871c670c29f30c34ef2a4ab5abc3b17d005/yagmail/sender.py#L22 , if you set the user, you will not be able to use the "from" field in the "result:email" part of the API request.
        host: smtp.myserver.com
        port: 25
        smtp_skip_login: true
        smtp_ssl: true
        smtp_starttls: true

    rest_api:  # Configuration of the REST API endpoint
      addr: 0.0.0.0
      port: 8080

Now, let's discuss main parts of this.

``templating`` section contains all definitions regarding the supported
PDF form templates.
In the section ``templating:fonts`` you can list additional fonts that can be
used in the PDF processing. Only TrueType fonts are supported for now.
The ``name`` parameter is used in the consequent references to the font in the
form field configurations.

The section ``templating:templates`` then includes list of all supported PDF
form templates. In this example, we support only one PDF form, called "MyForm".

Template definition
~~~~~~~~~~~~~~~~~~~

Each form template configuration then defines further configuration. ``id``
parameter defines ID that is used to select the particular form in the REST API
call (see the API section).

The ``template`` parameter defines which PDF file should be used as the "blank"
form to write the data over. There are two ways to select a PDF file:

* If only one PDF blank is used for all possible data contents, then the
  ``template:path`` parameter should provide path to a PDF file with the blank
  form.
* If the PDF blank should be different for different data contents, then the
  ``template:path`` parameter should be a path to a folder that contains files
  named in the ``template:path_value_substitution:pattern`` (the pattern format
  is the same as the Python `str.format()`_). The values in the pattern will
  be substituted by parameter defined in
  ``template:path_value_substitution:value``

So in our example, let's say the API call should include parameter ``user_id``
with value ``user33444``. Then, as the blank PDF form, file
``templates/myform_files/'myform_user33444_signed.pdf'`` will be used.

Form field elements
~~~~~~~~~~~~~~~~~~~

Each form template consists of several fields that are filled in. Byroapi
currently supports three field types:

* ``string`` - draws text string on a given coordinates.
* ``image``  - puts an image (from an image file) on a given coordinats.
* ``page_break`` - switches to the next page in case of a multi-page document.

Each of these fields can have further custom configurations. This configuration
can be done per-template (so this configuration is a default within a given
template) in the ``field_defaults`` section.

In the given example, we configure the ``string`` fields with default font
Arial, size 12 pts. This will be applied to the each ``string`` element within
the "MyForm" template.

Then, the individual fields are defined in the ``fields`` section. Each field
must contain ``name`` and ``type`` identifiers. The ``name`` identifiers is
matched against the data provided in the REST API call.

Field can also have a ``default`` value. That value is used if no value for
given field is provided in the API call.

Fields are processed in the order they are defined in the configuration.
Therefore, to fill a multi-page document, the field type ``page_break`` is used
to switch the pages. (for ``type: page_break`` fields, the ``name`` doesn't
matter but must be present, other fields do not have to be present and do
not matter).

Both ``string`` and ``image`` can have a ``custom`` property configuration that
overloads the default configuration. The contents of the ``custom`` is a list of
properties that match the `reportlab`_ setXXX() method calls using pattern
``set{property}(*{values})``.

Graphical fields also have the ``coords`` configuration property with ``x`` and
``y`` coordinates in millimeters from the bottom-left corner of the page (see
`reportlab`_ for details).

Email settings
~~~~~~~~~~~~~~

Depending on the API call paramters, one can request byroapi to send the
result of the PDF processing to a selected email address(es). For this, SMTP
is used, with configuration in ``email:smtp``. Each parameter of this section
should match the Yagmail_ sender config.

There are two ways how to configure the sender. If you use a SMTP server without
login process (usually an internal service), you don't use the ``user`` value in
the ``email:smtp`` and you can use it to emulate any sender address using the
``from`` parameter in the API call (see below).

If you SMTP server requires a login, then ``user`` parameter in ``email:smtp``
must be set and the ``from`` parameter in the api call will be ignored if
present.

REST API structure
++++++++++++++++++

The byroapi REST API provides two endpoints:

* POST ``/api/v1/form`` - for providing the form filling data and retrieving
  processed PDF file.
* PUT ``/api/v2/template/{template_id}/{var}`` - for updating the PDF blank files for each template


/api/v1/form
~~~~~~~~~~~~

Is a POST endpoint accepting JSON payload with following structure:

.. code-block:: json

    {
        "template": "template_id",
        "form_data": {
            "field_name": "field_value",
            ...
        },
        "result": {
            "download": true,
            "email": {
                "from": {"some@email.com": "Some Guy Name"},
                "to": {
                    "recipient1@email.com": "Recipient One",
                    "recipient2@email.com": "Recipient Two"
                },
                "cc": {...},
                "subject": "",
                "contents": "",
                "attachments": ""
            }
        }

    }

The ``template`` value shall match some ``id`` in the template configuration.

The section ``form_data`` then contains key-value collection where key matches
field names for and values are data to be filled into the form fields.

The ``result`` section then contains information about how to handle the result
of the PDF processing. If ``result:download`` is set to true, the PDF file will
be included in the REST response to the API call (otherwise, just status code
200 is returned in case of sucessful processing).

If ``result: email`` section (optional) is populated, then the PDF file will be
attached to an email and sent to the selected address. ``result:email:from``
needs to be filled only in case SMTP server doesn't use login (see the
`Email settings`_). The other parameters are matching the Yagmail_ send()
options. Only one attachment file is supported. If no file-name is defined,
a default file name will be used.

To continue with the example configuration from the `Configuration file`_ section
, the template "MyForm" can be processed with following JSON request:

.. code-block:: json

    {
        "template": "MyForm",
        "form_data": {
            "date_from": "2022/01/13",
            "date_to": "2022/01/14",
            "date_approved": "2022/01/12",
            "user_id": "user33444"
        },
        "result": {
            "download": true,
            "email":
                "to": {"some.guy@email.com": "Some Guy"},
                "subject": "My form processed",
                "contents": "My form is provided in attachment.",
                "attachments": "my_form_user33444.pdf"
        }
    }

/api/v1/template
~~~~~~~~~~~~~~~~

This PUT endpoint can be used for updates of the PDF "blank" files, especially in
case they use the path value substitution.
The use case is singular - a new or updated PDF "blank" for a given variable
value used in substitution can uploaded to the byroapi::

    $ curl -T new_template.pdf http://host:port/api/v1/template/{template_id}/{substitution_variable}

For example "MyForm" used above, "user33444" can update the PDF blank like
this::

    $ curl -T user33444_updated_blank.pdf http://host:port/api/v1/template/MyForm/user33444

This will update the existing platform in the substitution path, or add the new
one if none exists.

Usage
-----

Byroapi provides a simple CLI. To run as a server::

    $ byroapi --config your_config.yaml

To process PDF from CLI::

    $ byroapi --config your_config.yaml --fill-form your_form.yaml --output your_form_output.pdf

In this case, the ``your_form.yaml`` should be a YAML file with contents matching
the ``/api/v1/form`` JSON payload (only the ``template`` and ``form_data`` items
matter).

.. _`JNevrly/cookiecutter-pypackage-poetry`: https://github.com/JNevrly/cookiecutter-pypackage-poetry
.. _Onacol: https://github.com/calcite/onacol
.. _str.format(): https://docs.python.org/3/tutorial/inputoutput.html#the-string-format-method
.. _reportlab: https://www.reportlab.com/docs/reportlab-userguide.pdf
.. _Yagmail: https://github.com/kootenpv/yagmail/blob/f24af871c670c29f30c34ef2a4ab5abc3b17d005/yagmail/sender.py#L22
