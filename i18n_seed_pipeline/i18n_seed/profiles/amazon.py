from __future__ import annotations
import re
from . import DomainProfile

def amazon_profile() -> DomainProfile:
    # Lock SKUs and common marketplace-like IDs
    SKU_RE = re.compile(r"\b[A-Z0-9][A-Z0-9._-]+(?:-[A-Z0-9][A-Z0-9._-]+){2,}\b")
    MARKETPLACE_ID_RE = re.compile(r"\bA(?=[A-Z0-9]{13}\b)(?=.*\d)[A-Z0-9]{13}\b")

    return DomainProfile(
        id="amazon",
        placeholder_patterns=[SKU_RE, MARKETPLACE_ID_RE],
        system_rules=[
            "Do not alter SKUs or marketplace IDs.",
            "Translate human-readable values including product_type, attributes.style, sales_rank[].category, and common order/shipment enums.",
            "Where an address appears (e.g., shipping_address fields), rewrite it to a plausible address in the target locale but keep the original JSON key style (camelCase vs snake_case) intact.",
        ],
        force_include_columns={
            # ensure these columns are always extracted/translated
            "listings_items": {"product_type", "title", "description", "status"},
            "catalog_items": {"product_types", "attributes", "sales_ranks", "item_name", "product_type"},
            "order_items": {"title"},
            "inventory_summaries": {"product_name"},
            "product_pricing": {"status", "item_condition"},

        },
        json_string_keys={
            "title","item_name","name","description","brand","model","style",
            "category","display_name","value","heading","subtitle","bullet","label", "product_types", "product_type", "product_name", "status", "item_condition"
        },
        # json_overrides_by_locale={
        #     # ----------------------------- FRENCH (France) -----------------------------
        #     "fr_FR": [
        #         # currency + marketplace + addresses (schema-preserving handled in reinjector)
        #         {"table": "*", "column": "*", "json_path": "$..currency_code", "value": "EUR"},
        #         {"table": "*", "column": "*", "json_path": "$..marketplace_ids",
        #          "replace_array_value": ["ATVPDKIKX0DER"], "new_array_value": ["A13V1IB3VIYZZH"]},
        #         {"table": "*", "column": "*", "json_path": "$..shipping_address.countryCode", "value": "FR"},
        #         {"table": "*", "column": "*", "json_path": "$..shipping_address", "random_address": True},
        #         {"table": "*", "column": "*", "json_path": "$..billing_address",  "random_address": True},

        #         # ---- Order Status (fr) ----
        #         {"table":"*","column":"order_status","map_values":{
        #             # Pending
        #             "Pending":"En attente","PENDING":"En attente",
        #             # Pending Availability
        #             "PendingAvailability":"En attente de disponibilité",
        #             "Pending Availability":"En attente de disponibilité",
        #             "PENDING_AVAILABILITY":"En attente de disponibilité",
        #             "PENDING AVAILABILITY":"En attente de disponibilité",
        #             "pending-availability":"En attente de disponibilité",
        #             # Unshipped
        #             "Unshipped":"Non expédié","UNSHIPPED":"Non expédié",
        #             "UN_SHIPPED":"Non expédié","un-shipped":"Non expédié",
        #             # Partially Shipped
        #             "PartiallyShipped":"Partiellement expédié",
        #             "Partially Shipped":"Partiellement expédié",
        #             "PARTIALLY_SHIPPED":"Partiellement expédié",
        #             "PARTIALLY SHIPPED":"Partiellement expédié",
        #             "partially-shipped":"Partiellement expédié",
        #             # Shipped
        #             "Shipped":"Expédié","SHIPPED":"Expédié",
        #             # Canceled / Cancelled
        #             "Canceled":"Annulé","CANCELED":"Annulé",
        #             "Cancelled":"Annulé","CANCELLED":"Annulé",
        #             # Verified (seen in some feeds/workflows)
        #             "Verified":"Vérifié","VERIFIED":"Vérifié",
        #             "UNFULFILLABLE":"Non Réalisable"
        #         }},

        #         # ---- Shipment Status (fr) ----
        #         {"table":"*","column":"shipment_status","map_values":{
        #             # Pending
        #             "Pending":"En attente","PENDING":"En attente",
        #             # In Transit (all variants)
        #             "In Transit":"En transit","IN TRANSIT":"En transit",
        #             "InTransit":"En Transit",
        #             "IN_TRANSIT":"En transit","InTransit":"En transit",
        #             "in-transit":"En transit",
        #             # Delivered
        #             "Delivered":"Livré","DELIVERED":"Livré",
        #             # Out for Delivery (all variants)
        #             "Out for Delivery":"En cours de livraison",
        #             "OUT FOR DELIVERY":"En cours de livraison",
        #             "OUT_FOR_DELIVERY":"En cours de livraison",
        #             "OutForDelivery":"En cours de livraison",
        #             "out-for-delivery":"En cours de livraison",
        #             # Unshipped
        #             "Unshipped":"Non expédié","UNSHIPPED":"Non expédié",
        #             # Shipped to Customer (all variants)
        #             "Shipped to Customer":"Expédié au client",
        #             "SHIPPED TO CUSTOMER":"Expédié au client",
        #             "SHIPPED_TO_CUSTOMER":"Expédié au client",
        #             "ShippedToCustomer":"Expédié au client",
        #             "shipped-to-customer":"Expédié au client",
        #             # Delivery Attempted
        #             "Delivery Attempted":"Tentative de livraison",
        #             "DELIVERY ATTEMPTED":"Tentative de livraison",
        #             "DELIVERY_ATTEMPTED":"Tentative de livraison",
        #             "DeliveryAttempted":"Tentative de livraison",
        #             "delivery-attempted":"Tentative de livraison",
        #             # Returning / Returned
        #             "Returning":"Retour en cours","RETURNING":"Retour en cours",
        #             "Returned":"Retourné","RETURNED":"Retourné",
        #             # Delayed / Exception
        #             "Delayed":"Retardé","DELAYED":"Retardé",
        #             "Exception":"Exception","EXCEPTION":"Exception",
        #             # Picked Up / Ready for Pickup
        #             "Picked Up":"Retiré","PICKED UP":"Retiré",
        #             "PICKED_UP":"Retiré","PickedUp":"Retiré","picked-up":"Retiré",
        #             "Ready for Pickup":"Prêt pour retrait",
        #             "READY FOR PICKUP":"Prêt pour retrait",
        #             "READY_FOR_PICKUP":"Prêt pour retrait",
        #             "ReadyForPickup":"Prêt pour retrait",
        #             "ready-for-pickup":"Prêt pour retrait",
        #             "ReadyToShip":"Prêt pour expédition",
        #             "READY_TO_SHIP":"Prêt pour expédition",
        #             "LIVRÉ":"Livré",
        #             "EN_TRANSIT":"En transit",
        #             "NON_EXPÉDIÉ":"Non expédié",
        #             "SHIPPED":"Expédié",
        #             "UNSHIPPED":"Non expédié",
        #             "PENDINGPICKUP":"En attente de retrait","PENDING_PICKUP":"En attente de retrait","PendingPickup":"En attente de retrait",
        #             "LABELCANCELED":"Étiquette annulée","LABEL_CANCELED":"Étiquette annulée","LabelCanceled":"Étiquette annulée",
        #             "ATDESTINATIONFC":"Au centre de distribution de destination","AT_DESTINATION_FC":"Au centre de distribution de destination",
        #             "AtDestinationFC":"Au centre de distribution de destination",
        #             "UNDELIVERABLE":"Non livrable"
        #         }},

        #         # ---- Verification Status (fr) ----
        #         {"table":"*","column":"verification_status","map_values":{
        #             "Verified":"Vérifié","VERIFIED":"Vérifié"
        #         }},

        #         # ---- Payment Method (fr) : keep codes, translate generic bucket ----
        #         {"table":"*","column":"payment_method","map_values":{
        #         # Generic “other”
        #         "Others":"Autres", "OTHER":"Autres", "OTHER_PAYMENT":"Autres",
        #         # Cash on delivery
        #         "COD":"Paiement à la livraison", "C.O.D.":"Paiement à la livraison",
        #         "CashOnDelivery":"Paiement à la livraison", "CASH_ON_DELIVERY":"Paiement à la livraison",
        #         # Convenience store
        #         "CVS":"Magasin de proximité", "ConvenienceStore":"Magasin de proximité",
        #         "CONVENIENCE_STORE":"Magasin de proximité",
        #         # Cards
        #         "CreditCard":"Carte de crédit", "CREDIT_CARD":"Carte de crédit",
        #         "DebitCard":"Carte de débit",   "DEBIT_CARD":"Carte de débit",
        #         # Bank / cash / gift
        #         "BankTransfer":"Virement bancaire", "BANK_TRANSFER":"Virement bancaire",
        #         "Cash":"Espèces", "CASH":"Espèces",
        #         "GiftCard":"Carte-cadeau", "GIFT_CARD":"Carte-cadeau",
        #         # Invoice
        #         "Invoice":"Facture", "INVOICE":"Facture"
        #     }},
        #         {"table":"*","column":"verification_status","map_values":{
        #             # canonical + common variants (space/snake/case)
        #             "Pending":"En attente",
        #             "PENDING":"En attente",
        #             "PendingReview":"En attente de révision",
        #             "PENDING_REVIEW":"En attente de révision",
        #             "Verified":"Vérifié",
        #             "VERIFIED":"Vérifié",
        #             "Rejected":"Refusé",
        #             "REJECTED":"Refusé",
        #             "Approved":"Approuvé",
        #             "APPROVED":"Approuvé",
        #             "InformationRequired":"Informations requises",
        #             "INFORMATION_REQUIRED":"Informations requises",
        #             "Expired":"Expiré",
        #             "EXPIRED":"Expiré",
        #             "NotVerified":"Non vérifié",
        #             "NOT_VERIFIED":"Non vérifié"
        #         }},
        #     ],

        #     # ----------------------------- PORTUGUESE (Brazil) -----------------------------
        #     "pt_BR": [
        #         {"table": "*", "column": "*", "json_path": "$..currency_code", "value": "BRL"},
        #         {"table": "*", "column": "*", "json_path": "$..marketplace_ids",
        #          "replace_array_value": ["ATVPDKIKX0DER"], "new_array_value": ["A2Q3Y263D00KWC"]},
        #         {"table": "*", "column": "*", "json_path": "$..shipping_address.countryCode", "value": "BR"},
        #         {"table": "*", "column": "*", "json_path": "$..shipping_address", "random_address": True},
        #         {"table": "*", "column": "*", "json_path": "$..billing_address",  "random_address": True},

        #         # ---- Order Status (pt-BR) ----
        #         {"table":"*","column":"order_status","map_values":{
        #             # Pending
        #             "Pending":"Pendente","PENDING":"Pendente",
        #             # Pending Availability
        #             "PendingAvailability":"Pendente de disponibilidade",
        #             "Pending Availability":"Pendente de disponibilidade",
        #             "PENDING_AVAILABILITY":"Pendente de disponibilidade",
        #             "PENDING AVAILABILITY":"Pendente de disponibilidade",
        #             "pending-availability":"Pendente de disponibilidade",
        #             # Unshipped
        #             "Unshipped":"Não enviado","UNSHIPPED":"Não enviado",
        #             "UN_SHIPPED":"Não enviado","un-shipped":"Não enviado",
        #             # Partially Shipped
        #             "PartiallyShipped":"Parcialmente enviado",
        #             "Partially Shipped":"Parcialmente enviado",
        #             "PARTIALLY_SHIPPED":"Parcialmente enviado",
        #             "PARTIALLY SHIPPED":"Parcialmente enviado",
        #             "partially-shipped":"Parcialmente enviado",
        #             # Shipped
        #             "Shipped":"Enviado","SHIPPED":"Enviado",
        #             # Canceled / Cancelled
        #             "Canceled":"Cancelado","CANCELED":"Cancelado",
        #             "Cancelled":"Cancelado","CANCELLED":"Cancelado",
        #             # Verified
        #             "Verified":"Verificado","VERIFIED":"Verificado"
        #         }},
                

        #         # ---- Shipment Status (pt-BR) ----
        #         {"table":"*","column":"shipment_status","map_values":{
        #             # Pending
        #             "Pending":"Pendente","PENDING":"Pendente",
        #             # In Transit
        #             "In Transit":"Em Trânsito","IN TRANSIT":"Em Trânsito",
        #             "IN_TRANSIT":"Em Trânsito","InTransit":"Em Trânsito",
        #             "in-transit":"Em Trânsito",
        #             "InTransit":"EmTrânsito",
        #             # Delivered
        #             "Delivered":"Entregue","DELIVERED":"Entregue",
        #             # Out for Delivery
        #             "Out for Delivery":"Saiu para Entrega",
        #             "OUT FOR DELIVERY":"Saiu para Entrega",
        #             "OUT_FOR_DELIVERY":"Saiu para Entrega",
        #             "OutForDelivery":"Saiu para Entrega",
        #             "out-for-delivery":"Saiu para Entrega",
        #             # Unshipped
        #             "Unshipped":"Não Enviado","UNSHIPPED":"Não Enviado",
        #             # Shipped to Customer
        #             "Shipped to Customer":"Enviado ao Cliente",
        #             "SHIPPED TO CUSTOMER":"Enviado ao Cliente",
        #             "SHIPPED_TO_CUSTOMER":"Enviado ao Cliente",
        #             "ShippedToCustomer":"Enviado ao Cliente",
        #             "shipped-to-customer":"Enviado ao Cliente",
        #             # Delivery Attempted
        #             "Delivery Attempted":"Tentativa de Entrega",
        #             "DELIVERY ATTEMPTED":"Tentativa de Entrega",
        #             "DELIVERY_ATTEMPTED":"Tentativa de Entrega",
        #             "DeliveryAttempted":"Tentativa de Entrega",
        #             "delivery-attempted":"Tentativa de Entrega",
        #             # Returning / Returned
        #             "Returning":"Em Devolução","RETURNING":"Em Devolução",
        #             "Returned":"Devolvido","RETURNED":"Devolvido",
        #             # Delayed / Exception
        #             "Delayed":"Atrasado","DELAYED":"Atrasado",
        #             "Exception":"Exceção","EXCEPTION":"Exceção",
        #             # Picked Up / Ready for Pickup
        #             "Picked Up":"Retirado","PICKED UP":"Retirado",
        #             "PICKED_UP":"Retirado","PickedUp":"Retirado","picked-up":"Retirado",
        #             "Ready for Pickup":"Pronto para Retirada",
        #             "READY FOR PICKUP":"Pronto para Retirada",
        #             "READY_FOR_PICKUP":"Pronto para Retirada",
        #             "ReadyForPickup":"Pronto para Retirada",
        #             "ready-for-pickup":"Pronto para Retirada",
        #             "ReadyToShip":"Pronto para envio",
        #             "READY_TO_SHIP":"Pronto para envio",
        #             "ENTREGUE":"Entregue",
        #             "EM_TRANSITO":"Em Trânsito",
        #             "NAO_ENVIADO":"Não Enviado",  # without accent
        #             "NÃO_ENVIADO":"Não Enviado",  # with accent
        #             "SHIPPED":"Enviado",
        #             "UNSHIPPED":"Não Enviado"
        #         }},

        #         # ---- Verification Status (pt-BR) ----
        #         {"table":"*","column":"verification_status","map_values":{
        #             "Verified":"Verificado","VERIFIED":"Verificado"
        #         }},

        #         # ---- Payment Method (pt-BR) ----
        #         # Add inside json_overrides_by_locale["pt_BR"]
        #         {"table":"*","column":"payment_method","map_values":{
        #             # Generic “other”
        #             "Others":"Outros", "OTHER":"Outros", "OTHER_PAYMENT":"Outros",
        #             # Cash on delivery
        #             "COD":"Pagamento na entrega", "C.O.D.":"Pagamento na entrega",
        #             "CashOnDelivery":"Pagamento na entrega", "CASH_ON_DELIVERY":"Pagamento na entrega",
        #             # Convenience store
        #             "CVS":"Loja de conveniência", "ConvenienceStore":"Loja de conveniência",
        #             "CONVENIENCE_STORE":"Loja de conveniência",
        #             # Cards
        #             "CreditCard":"Cartão de crédito", "CREDIT_CARD":"Cartão de crédito",
        #             "DebitCard":"Cartão de débito",   "DEBIT_CARD":"Cartão de débito",
        #             # Bank / cash / gift
        #             "BankTransfer":"Transferência bancária", "BANK_TRANSFER":"Transferência bancária",
        #             "Cash":"Dinheiro", "CASH":"Dinheiro",
        #             "GiftCard":"Cartão-presente", "GIFT_CARD":"Cartão-presente",
        #             # Invoice
        #             "Invoice":"Fatura", "INVOICE":"Fatura"
        #         }},

        #         {"table":"*","column":"verification_status","map_values":{
        #             "Pending":"Pendente",
        #             "PENDING":"Pendente",
        #             "PendingReview":"Aguardando revisão",
        #             "PENDING_REVIEW":"Aguardando revisão",
        #             "Verified":"Verificado",
        #             "VERIFIED":"Verificado",
        #             "Rejected":"Rejeitado",
        #             "REJECTED":"Rejeitado",
        #             "Approved":"Aprovado",
        #             "APPROVED":"Aprovado",
        #             "InformationRequired":"Informações necessárias",
        #             "INFORMATION_REQUIRED":"Informações necessárias",
        #             "Expired":"Expirado",
        #             "EXPIRED":"Expirado",
        #             "NotVerified":"Não verificado",
        #             "NOT_VERIFIED":"Não verificado"
        #         }},
        #     ],

        #     # ----------------------------- SPANISH (Mexico) -----------------------------
        #     "es_MX": [
        #         {"table": "*", "column": "*", "json_path": "$..currency_code", "value": "MXN"},
        #         {"table": "*", "column": "*", "json_path": "$..marketplace_ids",
        #          "replace_array_value": ["ATVPDKIKX0DER"], "new_array_value": ["A1AM78C64UM0Y8"]},
        #         {"table": "*", "column": "*", "json_path": "$..shipping_address.countryCode", "value": "MX"},
        #         {"table": "*", "column": "*", "json_path": "$..shipping_address", "random_address": True},
        #         {"table": "*", "column": "*", "json_path": "$..billing_address",  "random_address": True},

        #         # ---- Order Status (es-MX) ----
        #         {"table":"*","column":"order_status","map_values":{
        #             # Pending
        #             "Pending":"Pendiente","PENDING":"Pendiente",
        #             # Pending Availability
        #             "PendingAvailability":"Pendiente de disponibilidad",
        #             "Pending Availability":"Pendiente de disponibilidad",
        #             "PENDING_AVAILABILITY":"Pendiente de disponibilidad",
        #             "PENDING AVAILABILITY":"Pendiente de disponibilidad",
        #             "pending-availability":"Pendiente de disponibilidad",
        #             # Unshipped
        #             "Unshipped":"No enviado","UNSHIPPED":"No enviado",
        #             "UN_SHIPPED":"No enviado","un-shipped":"No enviado",
        #             # Partially Shipped
        #             "PartiallyShipped":"Parcialmente enviado",
        #             "Partially Shipped":"Parcialmente enviado",
        #             "PARTIALLY_SHIPPED":"Parcialmente enviado",
        #             "PARTIALLY SHIPPED":"Parcialmente enviado",
        #             "partially-shipped":"Parcialmente enviado",
        #             # Shipped
        #             "Shipped":"Enviado","SHIPPED":"Enviado",
        #             # Canceled / Cancelled
        #             "Canceled":"Cancelado","CANCELED":"Cancelado",
        #             "Cancelled":"Cancelado","CANCELLED":"Cancelado",
        #             # Verified
        #             "Verified":"Verificado","VERIFIED":"Verificado"
        #         }},

        #         # ---- Shipment Status (es-MX) ----
        #         {"table":"*","column":"shipment_status","map_values":{
        #             # Pending
        #             "Pending":"Pendiente","PENDING":"Pendiente",
        #             # In Transit
        #             "In Transit":"En tránsito","IN TRANSIT":"En tránsito",
        #             "IN_TRANSIT":"En tránsito","InTransit":"En tránsito",
        #             "in-transit":"En tránsito",
        #             "InTransit":"EnTránsito",
        #             # Delivered
        #             "Delivered":"Entregado","DELIVERED":"Entregado",
        #             # Out for Delivery
        #             "Out for Delivery":"En reparto",
        #             "OUT FOR DELIVERY":"En reparto",
        #             "OUT_FOR_DELIVERY":"En reparto",
        #             "OutForDelivery":"En reparto",
        #             "out-for-delivery":"En reparto",
        #             # Unshipped
        #             "Unshipped":"No enviado","UNSHIPPED":"No enviado",
        #             # Shipped to Customer
        #             "Shipped to Customer":"Enviado al cliente",
        #             "SHIPPED TO CUSTOMER":"Enviado al cliente",
        #             "SHIPPED_TO_CUSTOMER":"Enviado al cliente",
        #             "ShippedToCustomer":"Enviado al cliente",
        #             "shipped-to-customer":"Enviado al cliente",
        #             # Delivery Attempted
        #             "Delivery Attempted":"Entrega intentada",
        #             "DELIVERY ATTEMPTED":"Entrega intentada",
        #             "DELIVERY_ATTEMPTED":"Entrega intentada",
        #             "DeliveryAttempted":"Entrega intentada",
        #             "delivery-attempted":"Entrega intentada",
        #             # Returning / Returned
        #             "Returning":"En devolución","RETURNING":"En devolución",
        #             "Returned":"Devuelto","RETURNED":"Devuelto",
        #             # Delayed / Exception
        #             "Delayed":"Retrasado","DELAYED":"Retrasado",
        #             "Exception":"Excepción","EXCEPTION":"Excepción",
        #             # Picked Up / Ready for Pickup
        #             "Picked Up":"Recogido","PICKED UP":"Recogido",
        #             "PICKED_UP":"Recogido","PickedUp":"Recogido","picked-up":"Recogido",
        #             "Ready for Pickup":"Listo para recoger",
        #             "READY FOR PICKUP":"Listo para recoger",
        #             "READY_FOR_PICKUP":"Listo para recoger",
        #             "ReadyForPickup":"Listo para recoger",
        #             "ready-for-pickup":"Listo para recoger",
        #             "ReadyToShip":"Listo para enviar",
        #             "READY_TO_SHIP":"Listo para enviar",
        #             "ENTREGADO":"Entregado",
        #             "EN_TRANSITO":"En tránsito",
        #             "NO_ENVIADO":"No enviado",
        #             "SHIPPED":"Enviado",
        #             "UNSHIPPED":"No enviado"
        #         }},

        #         # ---- Verification Status (es-MX) ----
        #         {"table":"*","column":"verification_status","map_values":{
        #             "Verified":"Verificado","VERIFIED":"Verificado"
        #         }},

        #         # ---- Payment Method (es-MX) ----
        #         # Add inside json_overrides_by_locale["es_MX"]
        #         {"table":"*","column":"payment_method","map_values":{
        #             # Generic “other”
        #             "Others":"Otros", "OTHER":"Otros", "OTHER_PAYMENT":"Otros",
        #             # Cash on delivery
        #             "COD":"Pago contra reembolso", "C.O.D.":"Pago contra reembolso",
        #             "CashOnDelivery":"Pago contra reembolso", "CASH_ON_DELIVERY":"Pago contra reembolso",
        #             # Convenience store
        #             "CVS":"Tienda de conveniencia", "ConvenienceStore":"Tienda de conveniencia",
        #             "CONVENIENCE_STORE":"Tienda de conveniencia",
        #             # Cards
        #             "CreditCard":"Tarjeta de crédito", "CREDIT_CARD":"Tarjeta de crédito",
        #             "DebitCard":"Tarjeta de débito",   "DEBIT_CARD":"Tarjeta de débito",
        #             # Bank / cash / gift
        #             "BankTransfer":"Transferencia bancaria", "BANK_TRANSFER":"Transferencia bancaria",
        #             "Cash":"Efectivo", "CASH":"Efectivo",
        #             "GiftCard":"Tarjeta de regalo", "GIFT_CARD":"Tarjeta de regalo",
        #             # Invoice
        #             "Invoice":"Factura", "INVOICE":"Factura"
        #         }},
        #         {"table":"*","column":"verification_status","map_values":{
        #             "Pending":"Pendiente",
        #             "PENDING":"Pendiente",
        #             "PendingReview":"Pendiente de revisión",
        #             "PENDING_REVIEW":"Pendiente de revisión",
        #             "Verified":"Verificado",
        #             "VERIFIED":"Verificado",
        #             "Rejected":"Rechazado",
        #             "REJECTED":"Rechazado",
        #             "Approved":"Aprobado",
        #             "APPROVED":"Aprobado",
        #             "InformationRequired":"Información requerida",
        #             "INFORMATION_REQUIRED":"Información requerida",
        #             "Expired":"Vencido",
        #             "EXPIRED":"Vencido",
        #             "NotVerified":"No verificado",
        #             "NOT_VERIFIED":"No verificado"
        #         }},
        #     ],
        # },
        json_overrides_by_locale={

            # ----------------------------- FRENCH (France) -----------------------------
            "fr_FR": [
                # currency + marketplace + addresses (schema-preserving; reinjector is alias-aware for currencyCode/currency_code)
                {"table":"*","column":"*","json_path":"$..currency_code","value":"EUR"},
                {"table":"*","column":"*","json_path":"$..marketplace_ids",
                 "replace_array_value":["ATVPDKIKX0DER"],"new_array_value":["A13V1IB3VIYZZH"]},
                {"table":"*","column":"*","json_path":"$..shipping_address.countryCode","value":"FR"},
                {"table":"*","column":"*","json_path":"$..shipping_address","random_address":True},
                {"table":"*","column":"*","json_path":"$..billing_address","random_address":True},

                # ---- Order Status (fr) ----
                {"table":"*","column":"order_status","map_values":{
                    "Pending":"En attente","PENDING":"En attente",
                    "PendingAvailability":"En attente de disponibilité",
                    "Pending Availability":"En attente de disponibilité",
                    "PENDING_AVAILABILITY":"En attente de disponibilité",
                    "PENDING AVAILABILITY":"En attente de disponibilité",
                    "pending-availability":"En attente de disponibilité",
                    "Unshipped":"Non expédié","UNSHIPPED":"Non expédié",
                    "UN_SHIPPED":"Non expédié","un-shipped":"Non expédié",
                    "PartiallyShipped":"Partiellement expédié",
                    "Partially Shipped":"Partiellement expédié",
                    "PARTIALLY_SHIPPED":"Partiellement expédié",
                    "PARTIALLY SHIPPED":"Partiellement expédié",
                    "partially-shipped":"Partiellement expédié",
                    "Shipped":"Expédié","SHIPPED":"Expédié",
                    "Canceled":"Annulé","CANCELED":"Annulé",
                    "Cancelled":"Annulé","CANCELLED":"Annulé",
                    "Verified":"Vérifié","VERIFIED":"Vérifié",
                    # NEW
                    "UNFULFILLABLE":"Non réalisable"
                }},

                # ---- Shipment Status (fr) ----
                {"table":"*","column":"shipment_status","map_values":{
                    "Pending":"En attente","PENDING":"En attente",
                    "In Transit":"En transit","IN TRANSIT":"En transit",
                    "IN_TRANSIT":"En transit","InTransit":"En transit","in-transit":"En transit",
                    "Delivered":"Livré","DELIVERED":"Livré",
                    "Out for Delivery":"En cours de livraison",
                    "OUT FOR DELIVERY":"En cours de livraison",
                    "OUT_FOR_DELIVERY":"En cours de livraison",
                    "OutForDelivery":"En cours de livraison","out-for-delivery":"En cours de livraison",
                    "Unshipped":"Non expédié","UNSHIPPED":"Non expédié",
                    "Shipped to Customer":"Expédié au client",
                    "SHIPPED TO CUSTOMER":"Expédié au client",
                    "SHIPPED_TO_CUSTOMER":"Expédié au client",
                    "ShippedToCustomer":"Expédié au client","shipped-to-customer":"Expédié au client",
                    "Delivery Attempted":"Tentative de livraison",
                    "DELIVERY ATTEMPTED":"Tentative de livraison",
                    "DELIVERY_ATTEMPTED":"Tentative de livraison",
                    "DeliveryAttempted":"Tentative de livraison","delivery-attempted":"Tentative de livraison",
                    "Returning":"Retour en cours","RETURNING":"Retour en cours",
                    "Returned":"Retourné","RETURNED":"Retourné",
                    "Delayed":"Retardé","DELAYED":"Retardé",
                    "Exception":"Exception","EXCEPTION":"Exception",
                    "Picked Up":"Retiré","PICKED UP":"Retiré",
                    "PICKED_UP":"Retiré","PickedUp":"Retiré","picked-up":"Retiré",
                    "Ready for Pickup":"Prêt pour retrait",
                    "READY FOR PICKUP":"Prêt pour retrait",
                    "READY_FOR_PICKUP":"Prêt pour retrait",
                    "ReadyForPickup":"Prêt pour retrait","ready-for-pickup":"Prêt pour retrait",
                    "ReadyToShip":"Prêt pour expédition","READY_TO_SHIP":"Prêt pour expédition",
                    "LIVRÉ":"Livré","EN_TRANSIT":"En transit","NON_EXPÉDIÉ":"Non expédié","SHIPPED":"Expédié","UNSHIPPED":"Non expédié",
                    # NEW variants
                    "PENDINGPICKUP":"En attente de retrait","PENDING_PICKUP":"En attente de retrait","PendingPickup":"En attente de retrait",
                    "LABELCANCELED":"Étiquette annulée","LABEL_CANCELED":"Étiquette annulée","LabelCanceled":"Étiquette annulée",
                    "ATDESTINATIONFC":"Au centre de distribution de destination","AT_DESTINATION_FC":"Au centre de distribution de destination",
                    "AtDestinationFC":"Au centre de distribution de destination",
                    "UNDELIVERABLE":"Non livrable"
                }},

                {"table":"*","column":"verification_status","map_values":{
                    "Verified":"Vérifié","VERIFIED":"Vérifié",
                    "Pending":"En attente","PENDING":"En attente",
                    "PendingReview":"En attente de révision","PENDING_REVIEW":"En attente de révision",
                    "Rejected":"Refusé","REJECTED":"Refusé",
                    "Approved":"Approuvé","APPROVED":"Approuvé",
                    "InformationRequired":"Informations requises","INFORMATION_REQUIRED":"Informations requises",
                    "Expired":"Expiré","EXPIRED":"Expiré",
                    "NotVerified":"Non vérifié","NOT_VERIFIED":"Non vérifié"
                }},

                # Payment Method (fr) – COD & CVS included
                {"table":"*","column":"payment_method","map_values":{
                    "Others":"Autres","OTHER":"Autres","OTHER_PAYMENT":"Autres",
                    "COD":"Paiement à la livraison","C.O.D.":"Paiement à la livraison",
                    "CashOnDelivery":"Paiement à la livraison","CASH_ON_DELIVERY":"Paiement à la livraison",
                    "CVS":"Magasin de proximité","ConvenienceStore":"Magasin de proximité","CONVENIENCE_STORE":"Magasin de proximité",
                    "CreditCard":"Carte de crédit","CREDIT_CARD":"Carte de crédit",
                    "DebitCard":"Carte de débit","DEBIT_CARD":"Carte de débit",
                    "BankTransfer":"Virement bancaire","BANK_TRANSFER":"Virement bancaire",
                    "Cash":"Espèces","CASH":"Espèces",
                    "GiftCard":"Carte-cadeau","GIFT_CARD":"Carte-cadeau",
                    "Invoice":"Facture","INVOICE":"Facture"
                }},
            ],

            # ----------------------------- PORTUGUESE (Brazil) -----------------------------
            "pt_BR": [
                {"table":"*","column":"*","json_path":"$..currency_code","value":"BRL"},
                {"table":"*","column":"*","json_path":"$..currencyCode","value":"BRL"},
                {"table":"*","column":"*","json_path":"$..CurrencyCode","value":"BRL"},
                {"table":"*","column":"*","json_path":"$..listingPrice.currencyCode","value":"BRL"},
                {"table":"*","column":"*","json_path":"$..shipping.currencyCode","value":"BRL"},
                {"table":"*","column":"*","json_path":"$..marketplace_ids",
                 "replace_array_value":["ATVPDKIKX0DER"],"new_array_value":["A2Q3Y263D00KWC"]},
                {"table":"*","column":"*","json_path":"$..shipping_address.countryCode","value":"BR"},
                {"table":"*","column":"*","json_path":"$..shipping_address","random_address":True},
                {"table":"*","column":"*","json_path":"$..billing_address","random_address":True},

                {"table":"*","column":"order_status","map_values":{
                    "Pending":"Pendente","PENDING":"Pendente",
                    "PendingAvailability":"Pendente de disponibilidade",
                    "Pending Availability":"Pendente de disponibilidade",
                    "PENDING_AVAILABILITY":"Pendente de disponibilidade",
                    "PENDING AVAILABILITY":"Pendente de disponibilidade",
                    "pending-availability":"Pendente de disponibilidade",
                    "Unshipped":"Não enviado","UNSHIPPED":"Não enviado","UN_SHIPPED":"Não enviado","un-shipped":"Não enviado",
                    "PartiallyShipped":"Parcialmente enviado","Partially Shipped":"Parcialmente enviado",
                    "PARTIALLY_SHIPPED":"Parcialmente enviado","PARTIALLY SHIPPED":"Parcialmente enviado","partially-shipped":"Parcialmente enviado",
                    "Shipped":"Enviado","SHIPPED":"Enviado",
                    "Canceled":"Cancelado","CANCELED":"Cancelado","Cancelled":"Cancelado","CANCELLED":"Cancelado",
                    "Verified":"Verificado","VERIFIED":"Verificado",
                    # NEW
                    "UNFULFILLABLE":"Impossível de atender"
                }},

                {"table":"*","column":"shipment_status","map_values":{
                    "Pending":"Pendente","PENDING":"Pendente",
                    "In Transit":"Em Trânsito","IN TRANSIT":"Em Trânsito",
                    "IN_TRANSIT":"Em Trânsito","InTransit":"Em Trânsito","in-transit":"Em Trânsito","InTransit":"EmTrânsito",
                    "Delivered":"Entregue","DELIVERED":"Entregue",
                    "Out for Delivery":"Saiu para Entrega","OUT FOR DELIVERY":"Saiu para Entrega",
                    "OUT_FOR_DELIVERY":"Saiu para Entrega","OutForDelivery":"Saiu para Entrega","out-for-delivery":"Saiu para Entrega",
                    "Unshipped":"Não Enviado","UNSHIPPED":"Não Enviado",
                    "Shipped to Customer":"Enviado ao Cliente","SHIPPED TO CUSTOMER":"Enviado ao Cliente",
                    "SHIPPED_TO_CUSTOMER":"Enviado ao Cliente","ShippedToCustomer":"Enviado ao Cliente","shipped-to-customer":"Enviado ao Cliente",
                    "Delivery Attempted":"Tentativa de Entrega","DELIVERY ATTEMPTED":"Tentativa de Entrega",
                    "DELIVERY_ATTEMPTED":"Tentativa de Entrega","DeliveryAttempted":"Tentativa de Entrega","delivery-attempted":"Tentativa de Entrega",
                    "Returning":"Em Devolução","RETURNING":"Em Devolução",
                    "Returned":"Devolvido","RETURNED":"Devolvido",
                    "Delayed":"Atrasado","DELAYED":"Atrasado",
                    "Exception":"Exceção","EXCEPTION":"Exceção",
                    "Picked Up":"Retirado","PICKED UP":"Retirado","PICKED_UP":"Retirado","PickedUp":"Retirado","picked-up":"Retirado",
                    "Ready for Pickup":"Pronto para Retirada","READY FOR PICKUP":"Pronto para Retirada",
                    "READY_FOR_PICKUP":"Pronto para Retirada","ReadyForPickup":"Pronto para Retirada","ready-for-pickup":"Pronto para Retirada",
                    "ReadyToShip":"Pronto para envio","READY_TO_SHIP":"Pronto para envio",
                    "ENTREGUE":"Entregue","EM_TRANSITO":"Em Trânsito","NAO_ENVIADO":"Não Enviado","NÃO_ENVIADO":"Não Enviado","SHIPPED":"Enviado","UNSHIPPED":"Não Enviado",
                    # NEW variants
                    "PENDINGPICKUP":"Pendente de retirada","PENDING_PICKUP":"Pendente de retirada","PendingPickup":"Pendente de retirada",
                    "LABELCANCELED":"Etiqueta cancelada","LABEL_CANCELED":"Etiqueta cancelada","LabelCanceled":"Etiqueta cancelada",
                    "ATDESTINATIONFC":"No centro de distribuição de destino","AT_DESTINATION_FC":"No centro de distribuição de destino",
                    "AtDestinationFC":"No centro de distribuição de destino",
                    "UNDELIVERABLE":"Impossível de entregar"
                }},

                {"table":"*","column":"verification_status","map_values":{
                    "Verified":"Verificado","VERIFIED":"Verificado",
                    "Pending":"Pendente","PENDING":"Pendente",
                    "PendingReview":"Aguardando revisão","PENDING_REVIEW":"Aguardando revisão",
                    "Rejected":"Rejeitado","REJECTED":"Rejeitado",
                    "Approved":"Aprovado","APPROVED":"Aprovado",
                    "InformationRequired":"Informações necessárias","INFORMATION_REQUIRED":"Informações necessárias",
                    "Expired":"Expirado","EXPIRED":"Expirado",
                    "NotVerified":"Não verificado","NOT_VERIFIED":"Não verificado"
                }},

                {"table":"*","column":"payment_method","map_values":{
                    "Others":"Outros","OTHER":"Outros","OTHER_PAYMENT":"Outros",
                    "COD":"Pagamento na entrega","C.O.D.":"Pagamento na entrega",
                    "CashOnDelivery":"Pagamento na entrega","CASH_ON_DELIVERY":"Pagamento na entrega",
                    "CVS":"Loja de conveniência","ConvenienceStore":"Loja de conveniência","CONVENIENCE_STORE":"Loja de conveniência",
                    "CreditCard":"Cartão de crédito","CREDIT_CARD":"Cartão de crédito",
                    "DebitCard":"Cartão de débito","DEBIT_CARD":"Cartão de débito",
                    "BankTransfer":"Transferência bancária","BANK_TRANSFER":"Transferência bancária",
                    "Cash":"Dinheiro","CASH":"Dinheiro",
                    "GiftCard":"Cartão-presente","GIFT_CARD":"Cartão-presente",
                    "Invoice":"Fatura","INVOICE":"Fatura"
                }},
            ],

            # ----------------------------- SPANISH (Mexico) -----------------------------
            "es_MX": [
                {"table":"*","column":"*","json_path":"$..currency_code","value":"MXN"},
                {"table":"*","column":"*","json_path":"$..marketplace_ids",
                 "replace_array_value":["ATVPDKIKX0DER"],"new_array_value":["A1AM78C64UM0Y8"]},
                {"table":"*","column":"*","json_path":"$..shipping_address.countryCode","value":"MX"},
                {"table":"*","column":"*","json_path":"$..shipping_address","random_address":True},
                {"table":"*","column":"*","json_path":"$..billing_address","random_address":True},

                {"table":"*","column":"order_status","map_values":{
                    "Pending":"Pendiente","PENDING":"Pendiente",
                    "PendingAvailability":"Pendiente de disponibilidad",
                    "Pending Availability":"Pendiente de disponibilidad",
                    "PENDING_AVAILABILITY":"Pendiente de disponibilidad",
                    "PENDING AVAILABILITY":"Pendiente de disponibilidad",
                    "pending-availability":"Pendiente de disponibilidad",
                    "Unshipped":"No enviado","UNSHIPPED":"No enviado","UN_SHIPPED":"No enviado","un-shipped":"No enviado",
                    "PartiallyShipped":"Parcialmente enviado","Partially Shipped":"Parcialmente enviado",
                    "PARTIALLY_SHIPPED":"Parcialmente enviado","PARTIALLY SHIPPED":"Parcialmente enviado","partially-shipped":"Parcialmente enviado",
                    "Shipped":"Enviado","SHIPPED":"Enviado",
                    "Canceled":"Cancelado","CANCELED":"Cancelado","Cancelled":"Cancelado","CANCELLED":"Cancelado",
                    "Verified":"Verificado","VERIFIED":"Verificado",
                    # NEW
                    "UNFULFILLABLE":"Imposible de cumplir"
                }},

                {"table":"*","column":"shipment_status","map_values":{
                    "Pending":"Pendiente","PENDING":"Pendiente",
                    "In Transit":"En tránsito","IN TRANSIT":"En tránsito",
                    "IN_TRANSIT":"En tránsito","InTransit":"En tránsito","in-transit":"En tránsito","InTransit":"EnTránsito",
                    "Delivered":"Entregado","DELIVERED":"Entregado",
                    "Out for Delivery":"En reparto","OUT FOR DELIVERY":"En reparto",
                    "OUT_FOR_DELIVERY":"En reparto","OutForDelivery":"En reparto","out-for-delivery":"En reparto",
                    "Unshipped":"No enviado","UNSHIPPED":"No enviado",
                    "Shipped to Customer":"Enviado al cliente","SHIPPED TO CUSTOMER":"Enviado al cliente",
                    "SHIPPED_TO_CUSTOMER":"Enviado al cliente","ShippedToCustomer":"Enviado al cliente","shipped-to-customer":"Enviado al cliente",
                    "Delivery Attempted":"Entrega intentada","DELIVERY ATTEMPTED":"Entrega intentada",
                    "DELIVERY_ATTEMPTED":"Entrega intentada","DeliveryAttempted":"Entrega intentada","delivery-attempted":"Entrega intentada",
                    "Returning":"En devolución","RETURNING":"En devolución",
                    "Returned":"Devuelto","RETURNED":"Devuelto",
                    "Delayed":"Retrasado","DELAYED":"Retrasado",
                    "Exception":"Excepción","EXCEPTION":"Excepción",
                    "Picked Up":"Recogido","PICKED UP":"Recogido","PICKED_UP":"Recogido","PickedUp":"Recogido","picked-up":"Recogido",
                    "Ready for Pickup":"Listo para recoger","READY FOR PICKUP":"Listo para recoger",
                    "READY_FOR_PICKUP":"Listo para recoger","ReadyForPickup":"Listo para recoger","ready-for-pickup":"Listo para recoger",
                    "ReadyToShip":"Listo para enviar","READY_TO_SHIP":"Listo para enviar",
                    "ENTREGADO":"Entregado","EN_TRANSITO":"En tránsito","NO_ENVIADO":"No enviado","SHIPPED":"Enviado","UNSHIPPED":"No enviado",
                    # NEW variants
                    "PENDINGPICKUP":"Pendiente de recolección","PENDING_PICKUP":"Pendiente de recolección","PendingPickup":"Pendiente de recolección",
                    "LABELCANCELED":"Etiqueta cancelada","LABEL_CANCELED":"Etiqueta cancelada","LabelCanceled":"Etiqueta cancelada",
                    "ATDESTINATIONFC":"En el centro de distribución de destino","AT_DESTINATION_FC":"En el centro de distribución de destino",
                    "AtDestinationFC":"En el centro de distribución de destino",
                    "UNDELIVERABLE":"No entregable"
                }},

                {"table":"*","column":"verification_status","map_values":{
                    "Verified":"Verificado","VERIFIED":"Verificado",
                    "Pending":"Pendiente","PENDING":"Pendiente",
                    "PendingReview":"Pendiente de revisión","PENDING_REVIEW":"Pendiente de revisión",
                    "Rejected":"Rechazado","REJECTED":"Rechazado",
                    "Approved":"Aprobado","APPROVED":"Aprobado",
                    "InformationRequired":"Información requerida","INFORMATION_REQUIRED":"Información requerida",
                    "Expired":"Vencido","EXPIRED":"Vencido",
                    "NotVerified":"No verificado","NOT_VERIFIED":"No verificado"
                }},

                {"table":"*","column":"payment_method","map_values":{
                    "Others":"Otros","OTHER":"Otros","OTHER_PAYMENT":"Otros",
                    "COD":"Pago contra reembolso","C.O.D.":"Pago contra reembolso",
                    "CashOnDelivery":"Pago contra reembolso","CASH_ON_DELIVERY":"Pago contra reembolso",
                    "CVS":"Tienda de conveniencia","ConvenienceStore":"Tienda de conveniencia","CONVENIENCE_STORE":"Tienda de conveniencia",
                    "CreditCard":"Tarjeta de crédito","CREDIT_CARD":"Tarjeta de crédito",
                    "DebitCard":"Tarjeta de débito","DEBIT_CARD":"Tarjeta de débito",
                    "BankTransfer":"Transferencia bancaria","BANK_TRANSFER":"Transferencia bancaria",
                    "Cash":"Efectivo","CASH":"Efectivo",
                    "GiftCard":"Tarjeta de regalo","GIFT_CARD":"Tarjeta de regalo",
                    "Invoice":"Factura","INVOICE":"Factura"
                }},
            ],
        },
    )


_BUILTIN_ADDRESS_POOLS: Dict[str, List[Dict[str, str]]] = {
    "fr_FR": [
        {"addressLine1":"14 Rue de Rivoli","city":"Paris","stateOrRegion":"Île-de-France","postalCode":"75004","countryCode":"FR"},
        {"addressLine1":"3 Avenue Jean Médecin","city":"Nice","stateOrRegion":"Provence-Alpes-Côte d'Azur","postalCode":"06000","countryCode":"FR"},
        {"addressLine1":"25 Rue de la République","city":"Lyon","stateOrRegion":"Auvergne-Rhône-Alpes","postalCode":"69002","countryCode":"FR"},
        {"addressLine1":"8 Rue Sainte-Catherine","city":"Bordeaux","stateOrRegion":"Nouvelle-Aquitaine","postalCode":"33000","countryCode":"FR"},
        {"addressLine1":"12 Rue des Carmes","city":"Toulouse","stateOrRegion":"Occitanie","postalCode":"31000","countryCode":"FR"},
        {"addressLine1":"5 Boulevard Saint-Michel","city":"Paris","stateOrRegion":"Île-de-France","postalCode":"75006","countryCode":"FR"},
        {"addressLine1":"22 Rue de la Paix","city":"Paris","stateOrRegion":"Île-de-France","postalCode":"75002","countryCode":"FR"},
        {"addressLine1":"17 Avenue Victor Hugo","city":"Paris","stateOrRegion":"Île-de-France","postalCode":"75116","countryCode":"FR"},
        {"addressLine1":"10 Rue du Faubourg Saint-Honoré","city":"Paris","stateOrRegion":"Île-de-France","postalCode":"75008","countryCode":"FR"},
        {"addressLine1":"3 Place du Capitole","city":"Toulouse","stateOrRegion":"Occitanie","postalCode":"31000","countryCode":"FR"},
        {"addressLine1":"4 Allée Jean Jaurès","city":"Nantes","stateOrRegion":"Pays de la Loire","postalCode":"44000","countryCode":"FR"},
        {"addressLine1":"56 Boulevard Gambetta","city":"Marseille","stateOrRegion":"Provence-Alpes-Côte d'Azur","postalCode":"13003","countryCode":"FR"},
        {"addressLine1":"9 Rue de Lille","city":"Lille","stateOrRegion":"Hauts-de-France","postalCode":"59000","countryCode":"FR"},
        {"addressLine1":"27 Rue du Président Wilson","city":"Strasbourg","stateOrRegion":"Grand Est","postalCode":"67000","countryCode":"FR"},
        {"addressLine1":"1 Cours Mirabeau","city":"Aix-en-Provence","stateOrRegion":"Provence-Alpes-Côte d'Azur","postalCode":"13100","countryCode":"FR"},
        {"addressLine1":"72 Rue Nationale","city":"Rouen","stateOrRegion":"Normandie","postalCode":"76000","countryCode":"FR"},
        {"addressLine1":"15 Rue de la Liberté","city":"Reims","stateOrRegion":"Grand Est","postalCode":"51100","countryCode":"FR"},
        {"addressLine1":"34 Boulevard Haussmann","city":"Paris","stateOrRegion":"Île-de-France","postalCode":"75008","countryCode":"FR"},
        {"addressLine1":"5 Rue Mouffetard","city":"Paris","stateOrRegion":"Île-de-France","postalCode":"75005","countryCode":"FR"},
        {"addressLine1":"20 Rue de la République","city":"Grenoble","stateOrRegion":"Auvergne-Rhône-Alpes","postalCode":"38000","countryCode":"FR"},
        {"addressLine1":"18 Rue des Fusillés","city":"Lyon","stateOrRegion":"Auvergne-Rhône-Alpes","postalCode":"69001","countryCode":"FR"},
        {"addressLine1":"7 Rue du Palais","city":"Poitiers","stateOrRegion":"Nouvelle-Aquitaine","postalCode":"86000","countryCode":"FR"},
        {"addressLine1":"14 Place de la Comédie","city":"Montpellier","stateOrRegion":"Occitanie","postalCode":"34000","countryCode":"FR"},
        {"addressLine1":"29 Quai de la Loire","city":"Nantes","stateOrRegion":"Pays de la Loire","postalCode":"44000","countryCode":"FR"},
        {"addressLine1":"10 Rue Saint-Louis","city":"Bordeaux","stateOrRegion":"Nouvelle-Aquitaine","postalCode":"33000","countryCode":"FR"},
        {"addressLine1":"45 Avenue Jean Jaurès","city":"Toulouse","stateOrRegion":"Occitanie","postalCode":"31000","countryCode":"FR"},
        {"addressLine1":"8 Rue d’Alsace Lorraine","city":"Lille","stateOrRegion":"Hauts-de-France","postalCode":"59000","countryCode":"FR"},
        {"addressLine1":"4 Rue de la Gare","city":"Lyon","stateOrRegion":"Auvergne-Rhône-Alpes","postalCode":"69003","countryCode":"FR"},
        {"addressLine1":"2 Boulevard Jean Moulin","city":"Marseille","stateOrRegion":"Provence-Alpes-Côte d'Azur","postalCode":"13005","countryCode":"FR"},
        {"addressLine1":"11 Rue Jeanne d’Arc","city":"Reims","stateOrRegion":"Grand Est","postalCode":"51100","countryCode":"FR"},
        {"addressLine1":"19 Rue du Général de Gaulle","city":"Nice","stateOrRegion":"Provence-Alpes-Côte d'Azur","postalCode":"06000","countryCode":"FR"},
        {"addressLine1":"9 Place du Parlement","city":"Bordeaux","stateOrRegion":"Nouvelle-Aquitaine","postalCode":"33000","countryCode":"FR"},
        {"addressLine1":"15 Avenue Victor Hugo","city":"Marseille","stateOrRegion":"Provence-Alpes-Côte d'Azur","postalCode":"13008","countryCode":"FR"},
        {"addressLine1":"38 Rue de la Loi","city":"Lille","stateOrRegion":"Hauts-de-France","postalCode":"59000","countryCode":"FR"},
        {"addressLine1":"22 Rue de Brest","city":"Rennes","stateOrRegion":"Brittany","postalCode":"35000","countryCode":"FR"},
        {"addressLine1":"7 Boulevard Carnot","city":"Tours","stateOrRegion":"Centre-Val de Loire","postalCode":"37000","countryCode":"FR"},
        {"addressLine1":"14 Cours Felix Faure","city":"Nice","stateOrRegion":"Provence-Alpes-Côte d'Azur","postalCode":"06000","countryCode":"FR"},
        {"addressLine1":"3 Rue Gambetta","city":"Nantes","stateOrRegion":"Pays de la Loire","postalCode":"44000","countryCode":"FR"},
        {"addressLine1":"12 Avenue Jean Jaurès","city":"Grenoble","stateOrRegion":"Auvergne-Rhône-Alpes","postalCode":"38000","countryCode":"FR"},
        {"addressLine1":"27 Rue des Trois Rois","city":"Strasbourg","stateOrRegion":"Grand Est","postalCode":"67000","countryCode":"FR"},
        {"addressLine1":"8 Boulevard Voltaire","city":"Dijon","stateOrRegion":"Bourgogne-Franche-Comté","postalCode":"21000","countryCode":"FR"},
        {"addressLine1":"5 Rue Pastourelle","city":"Marseille","stateOrRegion":"Provence-Alpes-Côte d'Azur","postalCode":"13005","countryCode":"FR"},
        {"addressLine1":"19 Rue Saint Michel","city":"Bordeaux","stateOrRegion":"Nouvelle-Aquitaine","postalCode":"33000","countryCode":"FR"},
        {"addressLine1":"24 Place de la République","city":"Lyon","stateOrRegion":"Auvergne-Rhône-Alpes","postalCode":"69001","countryCode":"FR"},
        {"addressLine1":"10 Rue de Verdun","city":"Le Havre","stateOrRegion":"Normandie","postalCode":"76600","countryCode":"FR"},
        {"addressLine1":"32 Avenue de la Grande Armée","city":"Paris","stateOrRegion":"Île-de-France","postalCode":"75017","countryCode":"FR"},
        {"addressLine1":"14 Rue Lafayette","city":"Rouen","stateOrRegion":"Normandie","postalCode":"76000","countryCode":"FR"},
        {"addressLine1":"18 Rue Sainte-Catherine","city":"Bordeaux","stateOrRegion":"Nouvelle-Aquitaine","postalCode":"33000","countryCode":"FR"},
        {"addressLine1":"11 Boulevard Jean Jaurès","city":"Toulouse","stateOrRegion":"Occitanie","postalCode":"31000","countryCode":"FR"},
        {"addressLine1":"6 Rue Gambetta","city":"Amiens","stateOrRegion":"Hauts-de-France","postalCode":"80000","countryCode":"FR"},
        {"addressLine1":"40 Rue Nationale","city":"Reims","stateOrRegion":"Grand Est","postalCode":"51100","countryCode":"FR"},

    ],
    "pt_BR": [
        {"addressLine1":"Av. Paulista, 1000","city":"São Paulo","stateOrRegion":"SP","postalCode":"01310-100","countryCode":"BR"},
        {"addressLine1":"Rua das Laranjeiras, 55","city":"Rio de Janeiro","stateOrRegion":"RJ","postalCode":"22240-003","countryCode":"BR"},
        {"addressLine1":"Av. Sete de Setembro, 1200","city":"Curitiba","stateOrRegion":"PR","postalCode":"80060-070","countryCode":"BR"},
        {"addressLine1":"Rua da Aurora, 250","city":"Recife","stateOrRegion":"PE","postalCode":"50050-000","countryCode":"BR"},
        {"addressLine1":"Av. Afonso Pena, 450","city":"Belo Horizonte","stateOrRegion":"MG","postalCode":"30130-000","countryCode":"BR"},
        {"addressLine1":"Rua XV de Novembro, 120","city":"Porto Alegre","stateOrRegion":"RS","postalCode":"90020-000","countryCode":"BR"},
        {"addressLine1":"Rua das Palmeiras, 320","city":"Manaus","stateOrRegion":"AM","postalCode":"69010-010","countryCode":"BR"},
        {"addressLine1":"Av. Amazonas, 5678","city":"Belo Horizonte","stateOrRegion":"MG","postalCode":"30190-000","countryCode":"BR"},
        {"addressLine1":"Rua do Comércio, 210","city":"Salvador","stateOrRegion":"BA","postalCode":"40020-000","countryCode":"BR"},
        {"addressLine1":"Otávio Mangabeira Ave, 150","city":"Salvador","stateOrRegion":"BA","postalCode":"40420-060","countryCode":"BR"},
        {"addressLine1":"Rua 24 de Outubro, 77","city":"Brasília","stateOrRegion":"DF","postalCode":"70040-020","countryCode":"BR"},
        {"addressLine1":"SQS 105 Bloco A, 45","city":"Brasília","stateOrRegion":"DF","postalCode":"70363-545","countryCode":"BR"},
        {"addressLine1":"Rua das Flores, 123","city":"São Paulo","stateOrRegion":"SP","postalCode":"01001-000","countryCode":"BR"},
        {"addressLine1":"Rua General Osório, 88","city":"Porto Alegre","stateOrRegion":"RS","postalCode":"90010-000","countryCode":"BR"},
        {"addressLine1":"Av. Brasil, 3500","city":"Rio de Janeiro","stateOrRegion":"RJ","postalCode":"20040-000","countryCode":"BR"},
        {"addressLine1":"Rua da Paz, 59","city":"Rio de Janeiro","stateOrRegion":"RJ","postalCode":"22041-001","countryCode":"BR"},
        {"addressLine1":"Travessa da Lapa, 10","city":"Rio de Janeiro","stateOrRegion":"RJ","postalCode":"20240-000","countryCode":"BR"},
        {"addressLine1":"Rua Santa Luzia, 5","city":"Fortaleza","stateOrRegion":"CE","postalCode":"60025-060","countryCode":"BR"},
        {"addressLine1":"Av. Beira Mar, 100","city":"Fortaleza","stateOrRegion":"CE","postalCode":"60165-121","countryCode":"BR"},
        {"addressLine1":"Rua Quinze de Novembro, 1400","city":"Porto Alegre","stateOrRegion":"RS","postalCode":"90080-000","countryCode":"BR"},
        {"addressLine1":"Rua Mato Grosso, 785","city":"Belo Horizonte","stateOrRegion":"MG","postalCode":"30150-180","countryCode":"BR"},
        {"addressLine1":"Rua São João, 325","city":"Curitiba","stateOrRegion":"PR","postalCode":"80020-000","countryCode":"BR"},
        {"addressLine1":"Av. Ipiranga, 1500","city":"Porto Alegre","stateOrRegion":"RS","postalCode":"90020-002","countryCode":"BR"},
        {"addressLine1":"Rua XV de Novembro, 1200","city":"Florianópolis","stateOrRegion":"SC","postalCode":"88010-270","countryCode":"BR"},
        {"addressLine1":"Rua do Catete, 150","city":"Rio de Janeiro","stateOrRegion":"RJ","postalCode":"22220-001","countryCode":"BR"},
        {"addressLine1":"Rua Conselheiro Lafaiete, 25","city":"Juiz de Fora","stateOrRegion":"MG","postalCode":"36010-220","countryCode":"BR"},
        {"addressLine1":"Av. Marechal Deodoro, 300","city":"Curitiba","stateOrRegion":"PR","postalCode":"80020-110","countryCode":"BR"},
        {"addressLine1":"Rua Coronel Dulcídio, 900","city":"Curitiba","stateOrRegion":"PR","postalCode":"80420-000","countryCode":"BR"},
        {"addressLine1":"Rua Ceará, 1024","city":"Manaus","stateOrRegion":"AM","postalCode":"69050-000","countryCode":"BR"},
        {"addressLine1":"Rua do Rosário, 99","city":"Belém","stateOrRegion":"PA","postalCode":"66010-000","countryCode":"BR"},
        {"addressLine1":"Rua Maria Júlia, 250","city":"São Paulo","stateOrRegion":"SP","postalCode":"01010-010","countryCode":"BR"},
        {"addressLine1":"Av. Presidente Vargas, 1500","city":"Rio de Janeiro","stateOrRegion":"RJ","postalCode":"20010-000","countryCode":"BR"},
        {"addressLine1":"Rua Barão do Rio Branco, 305","city":"Fortaleza","stateOrRegion":"CE","postalCode":"60025-020","countryCode":"BR"},
        {"addressLine1":"Travessa São José, 18","city":"Salvador","stateOrRegion":"BA","postalCode":"40020-020","countryCode":"BR"},
        {"addressLine1":"Rua XV de Novembro, 500","city":"Curitiba","stateOrRegion":"PR","postalCode":"80020-000","countryCode":"BR"},
        {"addressLine1":"Av. das Américas, 3000","city":"Rio de Janeiro","stateOrRegion":"RJ","postalCode":"22640-100","countryCode":"BR"},
        {"addressLine1":"Rua dos Andradas, 1200","city":"Porto Alegre","stateOrRegion":"RS","postalCode":"90020-000","countryCode":"BR"},
        {"addressLine1":"Rua Bahia, 975","city":"Belo Horizonte","stateOrRegion":"MG","postalCode":"30140-070","countryCode":"BR"},
        {"addressLine1":"Av. Paulista, 1578","city":"São Paulo","stateOrRegion":"SP","postalCode":"01310-200","countryCode":"BR"},
        {"addressLine1":"Rua Frei Serafim, 250","city":"Teresina","stateOrRegion":"PI","postalCode":"64000-000","countryCode":"BR"},
        {"addressLine1":"Rua Rui Barbosa, 210","city":"Natal","stateOrRegion":"RN","postalCode":"59010-000","countryCode":"BR"},
        {"addressLine1":"Rua 25 de Março, 400","city":"Piracicaba","stateOrRegion":"SP","postalCode":"13400-000","countryCode":"BR"},
        {"addressLine1":"Rua Marechal Deodoro, 800","city":"Florianópolis","stateOrRegion":"SC","postalCode":"88010-300","countryCode":"BR"},
        {"addressLine1":"Rua Amazonas, 1450","city":"Manaus","stateOrRegion":"AM","postalCode":"69010-000","countryCode":"BR"},
        {"addressLine1":"Av. São João, 500","city":"São Paulo","stateOrRegion":"SP","postalCode":"01035-010","countryCode":"BR"},
        {"addressLine1":"Rua Conselheiro Lafaiete, 100","city":"Juiz de Fora","stateOrRegion":"MG","postalCode":"36010-220","countryCode":"BR"},
        {"addressLine1":"Rua Rio Branco, 600","city":"Maceió","stateOrRegion":"AL","postalCode":"57020-000","countryCode":"BR"},
        {"addressLine1":"Av. Sete de Setembro, 1580","city":"Curitiba","stateOrRegion":"PR","postalCode":"80060-300","countryCode":"BR"},
        {"addressLine1":"Rua Joaquim Nabuco, 220","city":"Recife","stateOrRegion":"PE","postalCode":"50020-000","countryCode":"BR"},
        {"addressLine1":"Rua do Comércio, 2100","city":"Salvador","stateOrRegion":"BA","postalCode":"40020-200","countryCode":"BR"},
    ],
    "es_MX": [
        {"addressLine1":"Av. Paseo de la Reforma 222","city":"Ciudad de México","stateOrRegion":"CDMX","postalCode":"06500","countryCode":"MX"},
        {"addressLine1":"Av. Juárez 88","city":"Guadalajara","stateOrRegion":"JAL","postalCode":"44100","countryCode":"MX"},
        {"addressLine1":"Av. Hidalgo 350","city":"Monterrey","stateOrRegion":"NLE","postalCode":"64000","countryCode":"MX"},
        {"addressLine1":"Calle 60 #300","city":"Mérida","stateOrRegion":"YUC","postalCode":"97000","countryCode":"MX"},
        {"addressLine1":"Av. Hidalgo 21","city":"Puebla","stateOrRegion":"PUE","postalCode":"72000","countryCode":"MX"},
        {"addressLine1":"Calle Francisco I. Madero 15","city":"Ciudad de México","stateOrRegion":"CDMX","postalCode":"06000","countryCode":"MX"},
        {"addressLine1":"Callejón del Beso 17","city":"Guanajuato","stateOrRegion":"GTO","postalCode":"36000","countryCode":"MX"},
        {"addressLine1":"Calle Independencia 120","city":"León","stateOrRegion":"GTO","postalCode":"37000","countryCode":"MX"},
        {"addressLine1":"Av. Juárez 200","city":"Toluca","stateOrRegion":"MEX","postalCode":"50000","countryCode":"MX"},
        {"addressLine1":"Prolongación Zaragoza 45","city":"Tijuana","stateOrRegion":"BC","postalCode":"22000","countryCode":"MX"},
        {"addressLine1":"Boulevard Díaz Ordaz 105","city":"Monterrey","stateOrRegion":"NLE","postalCode":"64010","countryCode":"MX"},
        {"addressLine1":"Calle 8 Norte 34","city":"Villahermosa","stateOrRegion":"TAB","postalCode":"86000","countryCode":"MX"},
        {"addressLine1":"Callejon Sin Nombre 56","city":"Oaxaca","stateOrRegion":"OAX","postalCode":"68000","countryCode":"MX"},
        {"addressLine1":"Calle 1, Col. Centro","city":"Chihuahua","stateOrRegion":"CHIH","postalCode":"31000","countryCode":"MX"},
        {"addressLine1":"Calle Mina 78","city":"Zacatecas","stateOrRegion":"ZAC","postalCode":"98000","countryCode":"MX"},
        {"addressLine1":"Av. Universidad 200","city":"Guadalajara","stateOrRegion":"JAL","postalCode":"44150","countryCode":"MX"},
        {"addressLine1":"Calle 20 de Noviembre 90","city":"Parras de la Fuente","stateOrRegion":"COAH","postalCode":"27900","countryCode":"MX"},
        {"addressLine1":"Calle 5 Poniente 45","city":"Puebla","stateOrRegion":"PUE","postalCode":"72010","countryCode":"MX"},
        {"addressLine1":"Calle Hidalgo 123","city":"Tuxtla Gutiérrez","stateOrRegion":"CHIS","postalCode":"29000","countryCode":"MX"},
        {"addressLine1":"Av. Chapultepec 12","city":"Ciudad de México","stateOrRegion":"CDMX","postalCode":"11570","countryCode":"MX"},
        {"addressLine1":"Calle Reformada 67","city":"Querétaro","stateOrRegion":"QRO","postalCode":"76000","countryCode":"MX"},
        {"addressLine1":"Circuito Interior 1024","city":"Ciudad de México","stateOrRegion":"CDMX","postalCode":"06500","countryCode":"MX"},
        {"addressLine1":"Callejón García 30","city":"Guadalupe","stateOrRegion":"NLE","postalCode":"67100","countryCode":"MX"},
        {"addressLine1":"Callejón Rosales 11","city":"San Luis Potosí","stateOrRegion":"SLP","postalCode":"78000","countryCode":"MX"},
        {"addressLine1":"Boulevard Kukulcán Km 12","city":"Cancún","stateOrRegion":"ROO","postalCode":"77500","countryCode":"MX"},
        {"addressLine1":"Calle 16 de Septiembre 20","city":"Morelia","stateOrRegion":"MICH","postalCode":"58000","countryCode":"MX"},
        {"addressLine1":"Calle San Juan #5","city":"Aguascalientes","stateOrRegion":"AGS","postalCode":"20000","countryCode":"MX"},
        {"addressLine1":"Calle Juárez 300","city":"Ensenada","stateOrRegion":"BC","postalCode":"22800","countryCode":"MX"},
        {"addressLine1":"Calle Independencia 45","city":"Puebla","stateOrRegion":"PUE","postalCode":"72000","countryCode":"MX"},
        {"addressLine1":"Avenida Insurgentes Sur 1234","city":"Ciudad de México","stateOrRegion":"CDMX","postalCode":"03100","countryCode":"MX"},
        {"addressLine1":"Calle 5 de Mayo 321","city":"Guadalajara","stateOrRegion":"JAL","postalCode":"44100","countryCode":"MX"},
        {"addressLine1":"Calle Juárez 89","city":"Monterrey","stateOrRegion":"NLE","postalCode":"64000","countryCode":"MX"},
        {"addressLine1":"Av. Obregón 101","city":"Tijuana","stateOrRegion":"BC","postalCode":"22000","countryCode":"MX"},
        {"addressLine1":"Calle Zaragoza 222","city":"Morelia","stateOrRegion":"MICH","postalCode":"58000","countryCode":"MX"},
        {"addressLine1":"Calle Hidalgo 15","city":"Querétaro","stateOrRegion":"QRO","postalCode":"76000","countryCode":"MX"},
        {"addressLine1":"Camino Real 456","city":"Chihuahua","stateOrRegion":"CHIH","postalCode":"31000","countryCode":"MX"},
        {"addressLine1":"Av. Universidad 2000","city":"Ciudad de México","stateOrRegion":"CDMX","postalCode":"04510","countryCode":"MX"},
        {"addressLine1":"Calle 20 de Noviembre 77","city":"Ciudad Juárez","stateOrRegion":"CHIH","postalCode":"32000","countryCode":"MX"},
        {"addressLine1":"Avenida Reforma 220","city":"León","stateOrRegion":"GTO","postalCode":"37000","countryCode":"MX"},
        {"addressLine1":"Boulevard Independencia 500","city":"Tampico","stateOrRegion":"TAMPS","postalCode":"89000","countryCode":"MX"},
        {"addressLine1":"Calle 16 de Septiembre 180","city":"San Luis Potosí","stateOrRegion":"SLP","postalCode":"78000","countryCode":"MX"},
        {"addressLine1":"Calle Allende 34","city":"Oaxaca","stateOrRegion":"OAX","postalCode":"68000","countryCode":"MX"},
        {"addressLine1":"Callejón de la Amargura 5","city":"San Miguel de Allende","stateOrRegion":"GTO","postalCode":"37700","countryCode":"MX"},
        {"addressLine1":"Av. Juárez 450","city":"Puebla","stateOrRegion":"PUE","postalCode":"72010","countryCode":"MX"},
        {"addressLine1":"Av. Hidalgo 1234","city":"Acapulco","stateOrRegion":"GRO","postalCode":"39300","countryCode":"MX"},
        {"addressLine1":"Calle 1, Col. Centro","city":"Durango","stateOrRegion":"DGO","postalCode":"34000","countryCode":"MX"},
        {"addressLine1":"Carretera Nacional 45 150","city":"Saltillo","stateOrRegion":"COAH","postalCode":"25290","countryCode":"MX"},
        {"addressLine1":"Boulevard Kukulcán Km. 20","city":"Cancún","stateOrRegion":"ROO","postalCode":"77500","countryCode":"MX"},
    ],
}