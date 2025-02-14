// purchase_receipt.js

frappe.ui.form.on('Purchase Receipt', {
    refresh: function(frm) {
        // Add button for single document processing
        frm.add_custom_button(__('Process Single Document'), function() {
            uploadAndProcessDocument(frm, false);
        });

        // Add button for multiple document processing
        frm.add_custom_button(__('Process Multiple Documents'), function() {
            uploadAndProcessDocument(frm, true);
        });

        // Add button for generating multiple rows
        frm.add_custom_button(__('Generate Multiple Rows'), function() {
            showGenerateRowsDialog(frm);
        });
    }
});

function uploadAndProcessDocument(frm, multiple) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('Please add at least one item first.'));
        return;
    }

    // Configure uploader
    const uploader = new frappe.ui.FileUploader({
        doctype: 'Purchase Receipt',
        docname: frm.doc.name,
        folder: 'Home/Attachments',
        allow_multiple: multiple,
        on_success: (file_doc) => {
            // For multiple files, file_doc will be an array
            const files = multiple ? file_doc : [file_doc];
            const file_urls = files.map(f => f.file_url);
            
            // Show processing indicator
            frappe.show_alert({
                message: __('Processing document(s), please wait...'),
                indicator: 'blue'
            });
            
            // Make the API call
            frappe.call({
                method: multiple ? 'ocr.api.api.process_multiple_documents' : 'ocr.api.api.extract_document_data',
                args: {
                    docname: frm.doc.name,
                    file_urls: file_urls
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        const msg = multiple ? 
                            `Successfully processed ${r.message.total_files} documents with ${r.message.total_rows} total rows` :
                            `Successfully created ${r.message.rows_count} rows with data`;

                        frappe.show_alert({
                            message: __(msg),
                            indicator: 'green'
                        });

                        frm.reload_doc();
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('Error: ' + (r.message ? r.message.error : 'Unknown error'))
                        });
                    }
                }
            });
        }
    });

    uploader.show();
}

function showGenerateRowsDialog(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('Please add at least one item first.'));
        return;
    }

    let d = new frappe.ui.Dialog({
        title: 'Generate Multiple Rows',
        fields: [
            {
                label: 'Number of Rows',
                fieldname: 'num_rows',
                fieldtype: 'Int',
                reqd: 1,
                default: 1
            }
        ],
        primary_action_label: 'Generate',
        primary_action(values) {
            generateMultipleRows(frm, values.num_rows);
            d.hide();
        }
    });
    d.show();
}

function generateMultipleRows(frm, numRows) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frappe.msgprint(__('Please add at least one item first.'));
        return;
    }

    const templateRow = frm.doc.items[0];
    
    for (let i = 0; i < numRows; i++) {
        let row = frm.add_child('items', {
            'item_code': templateRow.item_code,
            'item_name': templateRow.item_name,
            'description': templateRow.description,
            'uom': templateRow.uom,
            'warehouse': templateRow.warehouse,
            'custom_attach_image': '',
            'custom_lot_no': '',
            'custom_reel_no': '',
            'qty': 0,
            'received_qty': 0,
            'accepted_qty': 0,
            'rejected_qty': 0
        });
    }
    
    frm.refresh_field('items');
    frappe.show_alert({
        message: __(`Generated ${numRows} new rows`),
        indicator: 'green'
    });
    
    frm.save()
        .then(() => {
            console.log(`Successfully generated ${numRows} rows`);
        })
        .catch(err => {
            console.error("Error saving document after generating rows:", err);
            frappe.msgprint(__('Error saving document after generating rows.'));
        });
}

// Row-level image processing
frappe.ui.form.on('Purchase Receipt Item', {
    custom_attach_image: async function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.custom_attach_image) {
            frappe.msgprint(__('Please upload an image.'));
            return;
        }

        try {
            await frm.save();
            
            frappe.call({
                method: 'ocr.api.api.extract_item_level_data',
                args: {
                    docname: frm.doc.name,
                    item_idx: row.idx
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __('Data extracted successfully!'),
                            indicator: 'green'
                        });
                        
                        frappe.model.set_value(cdt, cdn, {
                            'custom_lot_no': r.message.lot_no,
                            'custom_reel_no': r.message.reel_no,
                            'qty': r.message.qty,
                            'received_qty': r.message.qty,
                            'accepted_qty': r.message.qty,
                            'rejected_qty': 0
                        });
                        
                        frm.refresh_field('items');
                    } else {
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: __('Error: ' + (r.message ? r.message.error : 'Unknown error'))
                        });
                    }
                }
            });
        } catch (error) {
            console.error("Error processing image:", error);
            frappe.msgprint(__('Error processing the image. Please try again.'));
        }
    },
    
    // Add validation for quantity fields
    qty: function(frm, cdt, cdn) {
        validateQuantity(frm, cdt, cdn);
    },
    received_qty: function(frm, cdt, cdn) {
        validateQuantity(frm, cdt, cdn);
    },
    accepted_qty: function(frm, cdt, cdn) {
        validateQuantity(frm, cdt, cdn);
    },
    rejected_qty: function(frm, cdt, cdn) {
        validateQuantity(frm, cdt, cdn);
    }
});

// Helper function to validate quantities
function validateQuantity(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    
    // Ensure quantities are non-negative
    ['qty', 'received_qty', 'accepted_qty', 'rejected_qty'].forEach(field => {
        if (row[field] < 0) {
            frappe.model.set_value(cdt, cdn, field, 0);
            frappe.msgprint(__(`${field} cannot be negative`));
        }
    });
    
    // Validate that accepted + rejected = received
    if (row.accepted_qty + row.rejected_qty > row.received_qty) {
        frappe.msgprint(__('Sum of accepted and rejected quantities cannot exceed received quantity'));
        frappe.model.set_value(cdt, cdn, 'accepted_qty', row.received_qty - row.rejected_qty);
    }
}
